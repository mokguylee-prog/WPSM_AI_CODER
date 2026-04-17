# CLAUDE.md — WPSM_AI_CODER (Sm_AICoder)

## Project Purpose

월평동이상목 Sm_AICoder — 자연어 코드 생성 AI 서버 + GUI/CLI 클라이언트.
StarCoder2(코드 완성 전용)를 대체해 **자연어 지시**로 코드를 요청할 수 있는 환경.

- 백엔드: llama-cpp-python + GGUF 양자화 모델 (CPU 전용)
- 기본 모델: Qwen2.5-Coder-7B-Instruct-Q4_K_M (~4.4GB)
- 다중 턴 대화 히스토리 유지

## Environment Setup

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python.exe scripts\download_model.py
```

> llama-cpp-python 최신 버전이 MSVC 빌드 실패 시 `pip install llama-cpp-python==0.3.8`

## Run Commands

| 목적 | 명령어 |
| ---- | ------ |
| 환경 검증 | `venv\Scripts\python.exe scripts\check_env.py` |
| 모델 다운로드 | `venv\Scripts\python.exe scripts\download_model.py` |
| 서버 시작 | `.\start_server.ps1` |
| GUI 클라이언트 | `.\start_gui.ps1` |
| CLI 클라이언트 | `.\start_client.ps1` |
| 서버 종료 | `.\stop_server.ps1` |

## Architecture

```
WP_AI_CODER/
├── scripts/
│   ├── api_server.py       ← FastAPI 서버 (메인), /generate, /chat, /health, 대시보드
│   ├── download_model.py   ← HuggingFace Hub에서 GGUF 모델 다운로드
│   ├── check_env.py        ← 환경 검증
│   └── setup_d_drive.ps1   ← D드라이브 독립 설치용 스크립트
├── Sm_AICoder/
│   └── models/gguf/        ← GGUF 모델 파일 (서버가 자동으로 가장 큰 파일 선택)
├── gui_client.py            ← Tkinter GUI 클라이언트 (3패널)
├── client.py                ← 대화형 CLI 클라이언트
├── server.py                ← 백그라운드 서버 런처 (PID 관리)
├── start_server.ps1 / start_gui.ps1 / start_client.ps1 / stop_server.ps1
├── build_client.ps1         ← GUI 클라이언트 EXE 빌드 (PyInstaller)
└── docs/                    ← 설치/사용법/API 문서
```

## API Endpoints

| 엔드포인트 | 메서드 | 설명 |
| ---------- | ------ | ---- |
| `/` | GET | 웹 대시보드 |
| `/health` | GET | 서버/모델 상태 확인 |
| `/generate` | POST | 단발성 자연어 → 코드 |
| `/chat` | POST | 다중 턴 대화 (히스토리 포함) |
| `/stats` | GET | 요청 통계 + 최근 이력 |
| `/logs/download` | GET | 요청 로그 파일 다운로드 |

## Key Constants (scripts/api_server.py)

- `N_CTX = 4096` — 컨텍스트 길이
- `N_THREADS = 8` — CPU 스레드 수
- `N_GPU_LAYERS = 0` — CPU 전용
- `PORT = 8888`

## Repository

- GitHub: `mokguylee-prog/WPSM_AI_CODER`
