# PLAN.md — 에이전트 모드 안정화 계획

작성일: 2026-04-18
대상 증상: 에이전트 모드에서 "C# 으로 Winform 프로그램 만듭시다" 명령 실행 시
대시보드에 4건의 `[OpenFolder] D:\work_ai2\Robot_Dialog ...` 요청이 기록되고,
최종적으로 `[오류] LLM 응답을 받지 못했습니다.` 만 반환됨.

---

## 1. 현상 재현 데이터

| # | PROMPT_TOKENS | GEN_TOKENS | ELAPSED |
|---|---------------|------------|---------|
| 1 | 1,904         | 72         | 321,224 ms |
| 2 | 0             | 0          | 302,043 ms |
| 3 | 0             | 0          | 437,245 ms |
| 4 | 0             | 0          | 163,132 ms |

- 1번째 호출만 정상 응답(72토큰). 2~4번째는 0/0 토큰 + 300초대 경과 → **타임아웃**.
- 4건 모두 동일한 OpenFolder 프리픽스를 가진 동일 프롬프트.

---

## 2. 근본 원인 (Root Cause)

### 2.1 `_call_llm` 의 침묵형 예외 처리
[Sm_AIAgent/agent_loop.py:159-176](Sm_AIAgent/agent_loop.py#L159-L176)

```python
except requests.exceptions.ConnectionError:
    return None
except Exception:
    return None
```

- `requests.post(..., timeout=300)` 가 `ReadTimeout` 을 던지면 그대로 `None` 반환.
- 사용자에게는 `"[오류] LLM 응답을 받지 못했습니다."` 라는 단일 문자열만 표시.
- **무엇이** 실패했는지(타임아웃/연결끊김/JSON파싱) 알 길이 없음.

### 2.2 GUI가 매 메시지에 거대한 OpenFolder 컨텍스트를 자동 주입
[client/gui_client.py:1342-1372](client/gui_client.py#L1342-L1372)

- `_build_prompt_with_context` 가 `[OpenFolder]` + 폴더 트리(최대 200개) +
  선택 파일 전체 + 폴더 요약(앞 12개) 을 항상 프롬프트 앞에 붙임.
- 이번 케이스: 1,904 prompt 토큰. (사용자가 친 텍스트는 ~20토큰.)
- 에이전트 루프는 **매 iteration 마다** 이 프롬프트 + 누적된 도구 결과를
  `/chat` 으로 다시 전송 → 길이가 단조 증가.

### 2.3 로컬 모델 처리 한계 (CPU + Qwen2.5-Coder-7B Q4)
[server/scripts/api_server.py](server/scripts/api_server.py)

- `N_CTX = 8192`, `N_THREADS = 8`, `N_GPU_LAYERS = 0` (CPU 전용).
- 1,900토큰 입력 + 1,024 max_tokens 생성을 CPU 7B Q4_K_M 으로 돌리면
  보통 5–8 tok/s → 생성만 ~130–200초, 프리필 포함 **300초 초과 가능**.
- 1번째 응답이 321초 만에 72토큰만 내고 끝난 것이 그 증거(중간에 stop 또는 끊김).

### 2.4 JSON-in-text 도구 호출의 취약성
[Sm_AIAgent/agent_loop.py:178-211](Sm_AIAgent/agent_loop.py#L178-L211),
[Sm_AIAgent/prompts/system_prompt.py](Sm_AIAgent/prompts/system_prompt.py)

- Qwen 계열은 학습 시 XML 형태(`<tool_call>...`) tool-calling 에 익숙.
- 우리 프롬프트는 "JSON으로만 응답하라" 강제 → Qwen 이 일탈하여 prose 를 섞으면
  3단계 폴백 정규식이 모두 실패할 수 있음.
- llama-cpp-python 은 OpenAI-호환 `tool_calls` 와 `response_format=json_object`
  를 지원함에도 불구하고 사용하지 않음.

### 2.5 단계별 progress 가 GUI 에 도달하지 못함
- 에이전트 루프는 비스트리밍 `/chat` 만 호출 → 토큰이 들어오는 동안 클라이언트는
  완전 무응답으로 보임. heartbeat 만 흐름.
- 대시보드 4건은 동일 세션의 같은 사용자 입력에 대해 GUI 가 재시도(send 재호출)
  했거나, 사용자가 멈춘 줄 알고 다시 눌렀기 때문으로 추정. **취소되지 않은 채로
  서버에서는 계속 생성중**이었기 때문에 누적되어 보임.

### 2.6 4번 누적의 정확한 동선
- `/agent/run` 1회 → 내부 `/chat` 호출 1회 (성공, 72토큰) →
  도구 결과 추가 후 다음 `/chat` 호출 → 타임아웃 → `None` → 즉시 `[오류]` 반환.
- 그 사이 사용자/GUI가 다시 보내거나, 이전 호출이 서버 측에서 살아있어
  대시보드에는 4건의 `/chat` 으로 잡힘. (`/agent/*` 도 `/chat` 을 통과하므로
  대시보드의 "PROMPT" 가 OpenFolder 프리픽스로 표시됨.)

---

## 3. OpenCode / Claude Code / Qwen Code 의 대응 방식 조사 요약

| 항목 | 우리 현재 | 표준 사례 |
|------|-----------|-----------|
| Tool calling | system prompt 에 "JSON만 출력" 강제 + 정규식 파싱 | OpenAI-호환 `tool_calls` 또는 모델 native 형식(Qwen은 XML) |
| Loop 종결 조건 | `action == "answer"` | `stop_reason == "tool_use"` 분기 (Anthropic/Claude Code) |
| 컨텍스트 누적 | 매 턴마다 OpenFolder 1.9k 토큰 + 누적 메시지 | 시스템/툴 결과는 캐싱, 큰 파일은 요약·발췌, 폴더 트리는 1회만 |
| 스트리밍 | 비스트리밍 `/chat` | SSE/NDJSON 토큰 스트리밍 |
| 타임아웃 | 클라 300s 단일 제한, 실패 시 retry 없음 | 토큰별 idle-timeout, 백오프 retry, 부분 결과 보존 |
| 에러 표면화 | `Exception` 전부 삼킴 → `None` | 에러 종류별 메시지 + 재시도 안내 |
| 모델 선택 | Qwen2.5-Coder 7B CPU 만 | Qwen3-Coder 또는 GPU 오프로드 권장 (256K ctx) |

핵심 교훈 (출처 참조):
1. **로컬 7B는 정확한 JSON-only 출력을 잘 못한다.** 모델이 학습된 tool-call 포맷
   (Qwen → `<tool_call>`)을 그대로 쓰는 편이 수율이 높다.
2. **컨텍스트는 캐싱·발췌·요약이 핵심.** 폴더 트리·파일 본문을 매 턴 재전송하면
   CPU 추론은 사실상 멈춘다.
3. **반드시 스트리밍.** 사용자에게 "살아있다" 신호와 부분 결과를 노출.
4. **에러는 분류해서 보여준다.** 타임아웃/파싱실패/연결단절을 구분해야 사용자가
   재시도/취소 판단 가능.

---

## 4. 단계별 수정 계획

### Phase 1 — 즉시 가시성 확보 (당일 패치)

- [ ] **P1-1.** `_call_llm` 예외를 분류해서 호출자에게 사유를 돌려준다.
  - 반환 타입을 `Optional[str]` → `tuple[Optional[str], Optional[str]]`
    또는 `dict{"text", "error"}` 로 변경.
  - `ReadTimeout`, `ConnectionError`, 그 외 예외를 구분 메시지로 표면화.
  - 파일: [Sm_AIAgent/agent_loop.py:159-176](Sm_AIAgent/agent_loop.py#L159-L176)
- [ ] **P1-2.** `[오류] LLM 응답을 받지 못했습니다.` 대신 사유 포함:
  `[오류] LLM 응답 실패 (read-timeout 305s, prompt 1904 tokens)` 형태.
- [ ] **P1-3.** 도구 결과/Assistant 응답에 토큰 카운트 로그를 step 으로 emit.
  사용자가 어디서 멈췄는지 GUI 에서 확인 가능하게.

### Phase 2 — 컨텍스트 다이어트 (가장 큰 개선)

- [ ] **P2-1.** GUI: `_build_prompt_with_context` 를
      "**첫 턴에만 폴더 트리 / 파일요약 주입**" 으로 변경.
  - 두 번째 턴부터는 사용자가 친 텍스트만 전달.
  - 파일: [client/gui_client.py:1342-1372](client/gui_client.py#L1342-L1372)
- [ ] **P2-2.** 폴더 트리는 `[Folder files]` 의 상위 50개로 축소,
      `[Folder summaries]` 는 12 → 5개, 파일당 head 8 → 4 라인.
- [ ] **P2-3.** ContextManager: `max_chars 8000 → 4000`, `max_turns 10 → 6`,
      도구 결과 자르기 임계 `2000 → 800`.
  - 파일: [Sm_AIAgent/context_manager.py](Sm_AIAgent/context_manager.py)
- [ ] **P2-4.** 시스템 프롬프트의 한국어 길이 압축 (현 67줄 → 25줄 목표).
  핵심 규칙은 유지하되 중복 제거.

### Phase 3 — Tool Calling 신뢰도 개선

- [ ] **P3-1.** llama-cpp-python 의 `response_format={"type":"json_object"}` 를
      `/chat` 호출에 적용해 모델이 강제 JSON 출력하도록 함.
  - 파일: [server/scripts/api_server.py](server/scripts/api_server.py) (`chat` 핸들러)
- [ ] **P3-2.** Qwen native `<tool_call>...</tool_call>` 파서 추가
      → JSON 파서 실패 시 폴백.
  - 파일: [Sm_AIAgent/agent_loop.py:178-211](Sm_AIAgent/agent_loop.py#L178-L211)
- [ ] **P3-3.** JSON 파싱 실패 시 현재는 system 메시지 1회만 추가하고 재호출.
      재시도 횟수 제한(예: 2회) 후 `answer` 강제 종료해 무한 루프 방지.

### Phase 4 — 스트리밍 & 취소 강화

- [ ] **P4-1.** `/chat` 스트리밍(SSE)을 Agent 루프에서 사용.
      토큰 단위로 step 이벤트 발행 → GUI 가 "생성중 N 토큰" 표시.
- [ ] **P4-2.** **idle-timeout** 도입: 마지막 토큰 수신 후 N초 무응답이면 끊기.
      현재의 단일 300s 제한 폐기.
- [ ] **P4-3.** GUI: 동일 세션에서 in-flight 요청이 있을 때 send 버튼을 비활성화
      → 대시보드 중복 4건 누적 방지.
  - 파일: [client/gui_client.py](client/gui_client.py)

### Phase 5 — 모델/실행 환경 (선택적, 큰 효과)

- [ ] **P5-1.** `N_GPU_LAYERS` 를 환경에 따라 자동 조정. CUDA 가용 시 `-1`(전부).
- [ ] **P5-2.** Qwen3-Coder-7B 또는 Qwen2.5-Coder-1.5B 로 빠른 라우팅 옵션 추가
      (라우팅: 첫 턴은 큰 모델, 이후 도구 호출은 작은 모델).
- [ ] **P5-3.** 시스템/도구 스키마는 변하지 않으므로 prompt cache 활용
      (`cache_prompt` is not passed to `create_chat_completion` in the current server).

### Phase 6 — 회귀 검증

- [x] **P6-1.** 동일 입력 ("C# WinForm 만듭시다") + OpenFolder 지정으로 e2e 시나리오 스크립트.
- [x] **P6-2.** 토큰 사용량 기준 가드 (prompt > 3000 토큰이면 경고 step).
- [x] **P6-3.** 대시보드에 `kind="agent-step"` 컬럼 분리해 chat 호출과 구분.

---

## 5. 우선순위 / 예상 효과

| Phase | 난이도 | 예상 효과 | 우선순위 |
|-------|--------|-----------|----------|
| 1     | 낮음   | 디버깅 가능해짐 | ★★★★★ 즉시 |
| 2     | 낮음   | 1.9k → ~400 토큰, 추론시간 1/3 | ★★★★★ 즉시 |
| 3     | 중간   | JSON 파싱 실패율 감소 | ★★★★ |
| 4     | 중간   | UX 개선, 중복 호출 제거 | ★★★★ |
| 5     | 높음   | 토큰/s 5–10배 (GPU 시) | ★★★ |
| 6     | 낮음   | 회귀 방지 | ★★★ |

**제안 진입 순서**: P1-1 → P1-2 → P2-1 → P2-3 → P3-1 → P4-3 → 나머지.

---

## 6. 참고 자료 (Sources)

- [How Coding Agents Actually Work: Inside OpenCode — Moncef Abboud](https://cefboud.com/posts/coding-agents-internals-opencode-deepdive/)
- [Coding Agent with Self-hosted LLM (Opencode + vLLM)](https://cefboud.com/posts/coding-agent-self-hosted-llm-opencode-vllm/)
- [OpenCode CLI Guide 2026: Local LLMs with Ollama](https://yuv.ai/learn/opencode-cli)
- [Best Local LLMs for OpenClaw Agents in 2026](https://www.clawctl.com/blog/best-local-llm-coding-2026)
- [Claude Code: Behind-the-scenes of the master agent loop](https://blog.promptlayer.com/claude-code-behind-the-scenes-of-the-master-agent-loop/)
- [How Claude Code works — Claude Code Docs](https://code.claude.com/docs/en/how-claude-code-works)
- [Qwen Code CLI: Tool Definitions, Architecture (2026)](https://www.morphllm.com/qwen-code)
- [Qwen3-Coder: Agentic Coding in the World](https://qwenlm.github.io/blog/qwen3-coder/)
- [Qwen3-Coder GGUF Tool Calling Fixes (Unsloth)](https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF/discussions/10)
