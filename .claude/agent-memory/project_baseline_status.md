---
name: project_baseline_status
description: 2026-04-18 baseline 측정값 — 에이전트 모드 타임아웃 패턴 및 각 엔드포인트 상태
type: project
---

## Baseline 측정일: 2026-04-18 (PLAN.md 작성 직후, 코드 수정 전)

### 환경
- Python 3.13.12, llama-cpp-python OK, FastAPI 0.136.0
- 모델: qwen2.5-coder-7b-instruct-q4_k_m.gguf (4.4GB) — 정상 로드

### 엔드포인트 상태
| 엔드포인트 | 상태 | 응답시간 | 비고 |
|---|---|---|---|
| /health | PASS | 즉시 | model 정상 로드 확인 |
| /generate | PASS | ~18초 | 짧은 prompt 정상 |
| /chat | PASS | ~5초 | 단순 1턴 OK |
| /stats | PASS | 즉시 | 히스토리 포함 |
| /agent/sessions | PASS | 즉시 | |
| /agent/reset | PASS | 즉시 | |
| /agent/run | FAIL | 300s timeout | 1,401 prompt 토큰, 65 gen 토큰 생성 후 다음 /chat 호출 시 타임아웃 |

### 재현된 4건 누적 패턴 (로그 requests_20260418024009.log)
- id=1 (chat): prompt=1,904토큰, gen=72, elapsed=321,224ms → 1번째 /chat 성공
- id=2 (agent): prompt=0, gen=0, elapsed=302,043ms → /agent/run [오류] LLM 응답 못받음
- id=3 (chat): prompt=0, gen=0, elapsed=437,245ms → 2번째 /chat 타임아웃
- id=4 (chat): prompt=0, gen=0, elapsed=163,132ms → 3번째 /chat 타임아웃

### 스모크 테스트 중 확인된 추가 패턴
- 스모크 agent/run (list_files 요청): prompt_tok=1,401, gen_tok=65, elapsed=301,494ms → 타임아웃
- 원인 동일: 1,400토큰 프롬프트 + max_tokens=256 생성 = CPU 7B Q4에서 300초 초과

### 중요 발견
- /chat 은 curl에서 "There was an error parsing the body" 반환 → Python urllib로 호출 시 정상
  (curl의 멀티라인 JSON 이스케이프 문제, API 자체 버그 아님)
- agent/run은 내부적으로 /chat을 호출하며, OpenFolder 컨텍스트 포함 시 1,400~1,900 토큰이 매 iteration 전송됨
- 서버는 계속 살아있고 생성을 완료하지만, client 300s timeout이 먼저 발동함

**Why:** PLAN.md Phase 2 (컨텍스트 다이어트)가 즉각적으로 필요한 이유를 수치로 확인
**How to apply:** Phase 1+2 수정 후 동일 시나리오로 재측정하여 elapsed_ms 1/3 감소 확인
