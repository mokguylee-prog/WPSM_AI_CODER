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
