# CLAUDE.md — Sm_AICoder

## Project Purpose

Instruction-following 코드 생성 프레임워크. StarCoder2(코드 완성 전용)를 대체해
**자연어 지시**로 코드를 요청할 수 있는 환경을 구성한다.

- 백엔드: llama-cpp-python + GGUF 양자화 모델 (CPU 전용)
- 기본 모델: Qwen2.5-Coder-7B-Instruct-Q4_K_M (~4.4GB)
- 다중 턴 대화 히스토리 유지

## 왜 StarCoder2가 아닌가

StarCoder2는 code completion 모델 — 부분 코드를 넣으면 나머지를 채운다.
자연어 지시("circle 그리는 코드 만들어줘")를 이해하지 못한다.
Qwen2.5-Coder-Instruct는 instruction-following 모델로 Claude처럼 쓸 수 있다.

## Environment Setup

```powershell
# 프로젝트 디렉토리에서 가상환경 생성
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

## Run Commands

| 목적 | 명령어 |
|------|--------|
| 환경 검증 | `python scripts/check_env.py` |
| 모델 다운로드 | `python scripts/download_model.py` |
| 서버 시작 (백그라운드) | `.\start_server.ps1` |
| 클라이언트 실행 | `.\start_client.ps1` |
| 서버 종료 | `.\stop_server.ps1` |

## Architecture

```
scripts/api_server.py  ← FastAPI + llama-cpp-python, /generate, /chat, /health
client.py              ← 대화형 CLI, 다중 턴 히스토리 유지
server.py              ← 백그라운드 런처 (PID 관리)
```

## API Endpoints

| 엔드포인트 | 설명 |
|-----------|------|
| `POST /generate` | 단발성 자연어 → 코드 |
| `POST /chat` | 다중 턴 대화 (히스토리 포함) |
| `GET /health` | 서버/모델 상태 확인 |

## Model Directory

GGUF 파일 위치: `models/gguf/*.gguf` (프로젝트 상대경로)
서버가 자동으로 가장 큰 .gguf 파일을 선택한다.

## Key Constants

- `N_CTX = 4096` — 컨텍스트 길이
- `N_THREADS = 8` — CPU 스레드 수 (core 수에 맞게 조정)
- `PORT = 8888`
