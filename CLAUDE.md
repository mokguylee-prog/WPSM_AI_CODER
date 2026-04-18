# CLAUDE.md for WPSM_AI_CODER (Sm_AICoder)

## 프로젝트 목적

Sm_AICoder는 로컬 코드 생성 프로젝트입니다.

- 백엔드: `llama-cpp-python` + GGUF 모델
- 클라이언트: GUI/CLI
- 에이전트 루프: `Sm_AIAgent` (선택)

기본 모델:

- `Qwen2.5-Coder-7B-Instruct-Q4_K_M` (약 4.4GB)

## 환경 설정

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python.exe server\scripts\download_model.py
```

Windows에서 `llama-cpp-python` 최신 빌드가 실패하면:

```powershell
pip install llama-cpp-python==0.3.8
```

## 실행 명령어

| 목적 | 명령어 |
| ---- | ------ |
| 환경 점검 | `venv\Scripts\python.exe server\scripts\check_env.py` |
| 모델 다운로드 | `venv\Scripts\python.exe server\scripts\download_model.py` |
| 서버 시작 | `.\\start_server.ps1` |
| GUI 클라이언트 실행 | `.\\start_gui.ps1` |
| CLI 클라이언트 실행 | `.\\start_client.ps1` |
| Agent CLI 실행 | `.\\start_agent.ps1` |
| 서버 종료 | `.\\stop_server.ps1` |

## 구조

```text
WP_AI_CODER/
├── client/
│   ├── gui_client.py
│   ├── client.py
│   ├── agent_client.py
│   ├── make_icon.py
│   └── Sm_AiCoderClient.exe
├── server/
│   ├── server.py
│   ├── logs/
│   └── scripts/
│       ├── api_server.py
│       ├── download_model.py
│       ├── check_env.py
│       └── setup_d_drive.ps1
├── Sm_AICoder/
│   └── models/gguf/
├── Sm_AIAgent/
│   ├── agent_loop.py
│   ├── agent_api.py
│   ├── context_manager.py
│   ├── config.py
│   ├── Sm_AIAgent_config.json
│   ├── tools/
│   │   ├── registry.py
│   │   ├── file_tools.py
│   │   ├── code_tools.py
│   │   └── command_tools.py
│   └── prompts/
│       └── system_prompt.py
├── build_client.ps1
├── start_server.ps1
├── stop_server.ps1
├── start_gui.ps1
├── start_client.ps1
├── start_agent.ps1
└── docs/
```

## API 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
| ---------- | ------ | ---- |
| `/` | GET | 대시보드 |
| `/health` | GET | 서버/모델 상태 |
| `/generate` | POST | 단일 프롬프트 생성 |
| `/chat` | POST | 대화형 생성 |
| `/stats` | GET | 요청 통계 + 최근 이력 |
| `/logs/download` | GET | 요청 로그 다운로드 |
| `/agent/run` | POST | 에이전트 루프 실행 |
| `/agent/stream` | POST | 에이전트 스트리밍 실행 (NDJSON) |
| `/agent/reset` | POST | 세션 초기화 |
| `/agent/sessions` | GET | 활성 세션 목록 |

## 주요 상수 (`server/scripts/api_server.py`)

- `N_CTX = 8192`
- `N_THREADS = 8`
- `N_GPU_LAYERS = 0`
- `PORT = 8888`

## 저장소

- GitHub: `mokguylee-prog/WPSM_AI_CODER`

## 개발 워크플로 (오케스트레이터 주관)

모든 기능 추가·버그 수정·리팩터링은 **`orchestrator-agent`** 가 주관한다.
직접 코드를 수정하지 말고 아래 흐름을 따를 것.

### 역할 분담

| 에이전트 | 역할 |
| -------- | ---- |
| `orchestrator-agent` | 전체 루프 조율, 진행 막힘 감지, 폴백 전략 결정 |
| `designer-agent` | 설계·아키텍처 결정, 실패 모드 분석 |
| `developer-agent` | 코드 구현, 버그 수정, 반복 개선 |
| `evaluator-agent` | 품질 스코어카드 검증, 통과/실패 판정 |

### 표준 루프

```
orchestrator → designer (설계)
             → developer (구현)
             → evaluator (검증)
             → [점수 < 95이면 반복 / ≥ 95이면 종료]
```

### 막힘(Stall) 처리

같은 갭에서 2회 연속 점수 개선이 없으면 오케스트레이터가 다음 순서로 우회한다.

1. 루트 원인 재분석 (`designer-agent` 새 관점으로 재시도)
2. 다른 구현 방식 (`developer-agent` 다른 접근법으로 재구현)
3. 최소 재현 테스트 작성 후 해당 테스트 먼저 수정
4. 마지막 변경 Revert 후 처음부터 재설계
5. 웹 검색으로 선행 사례 조사 후 컨텍스트 주입

### 규칙

- 같은 실패 방식을 2회 이상 반복하지 않는다.
- 게이트를 통과하지 못한 코드는 머지하지 않는다.
- 점수가 "대부분 수정됨" 상태에서 멈추지 않는다.
