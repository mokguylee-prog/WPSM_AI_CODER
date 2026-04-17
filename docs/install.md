# WP_AI_CODER 서버 설치 기록

> 설치 일시: 2026-04-17
> 설치 환경: Windows 11 Pro, Python 3.13

---

## 1단계: 환경 확인

```bash
# Python 버전 확인
python --version
# 결과: Python 3.14.3

# 사용 가능한 Python 경로 확인
where python
# 결과:
# C:\Python314\python.exe
# C:\Users\kadelee\AppData\Local\Programs\Python\Python313\python.exe
# C:\Users\kadelee\AppData\Local\Microsoft\WindowsApps\python.exe

# 기존 venv 존재 여부 확인
ls D:/Sm_AICoder/venv/Scripts/python.exe
# 결과: 존재하지 않음 (D:/Sm_AICoder 디렉토리 자체가 없음)

# 모델 파일 존재 여부 확인
ls D:/Sm_AICoder/models/gguf/*.gguf
# 결과: 존재하지 않음

# 필요 패키지 설치 여부 확인
pip list | grep -iE "llama|fastapi|uvicorn|pydantic"
# 결과: 미설치
```

---

## 2단계: 가상환경 생성 (Python 3.13 사용)

```bash
# Python 3.14는 llama-cpp-python 호환 문제 가능성이 있어 3.13 사용
cd d:/WP_AI_CODER
"C:/Users/kadelee/AppData/Local/Programs/Python/Python313/python.exe" -m venv venv

# pip 업그레이드
venv/Scripts/python.exe -m pip install --upgrade pip

# 의존성 설치 (llama-cpp-python C++ 빌드 포함, 5~10분 소요)
venv/Scripts/pip.exe install -r requirements.txt
```

---

## 3단계: 경로 수정 (D:/Sm_AICoder -> 프로젝트 상대경로)

원래 코드가 `D:/Sm_AICoder`으로 하드코딩되어 있어서 아래 파일들을 수정함.

### scripts/api_server.py

```python
# 변경 전
MODEL_DIR = "D:/Sm_AICoder/models/gguf"
LOG_DIR   = "logs"

# 변경 후
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR  = os.path.join(BASE_DIR, "models", "gguf")
LOG_DIR    = os.path.join(BASE_DIR, "logs")
```

### scripts/download_model.py

```python
# 변경 전
SAVE_DIR = "D:/Sm_AICoder/models/gguf"

# 변경 후
SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "gguf")
```

### start_server.ps1 / start_gui.ps1 / start_client.ps1 / build_client.ps1

```powershell
# 변경 전
$venv = "D:\Sm_AICoder\venv\Scripts\python.exe"
if (-not (Test-Path $venv)) { $venv = "python" }

# 변경 후
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $scriptDir "venv\Scripts\python.exe"
if (-not (Test-Path $venv)) { $venv = "python" }
```

### CLAUDE.md

```
# 변경 전
python -m venv D:\Sm_AICoder\venv
GGUF 파일 위치: D:/Sm_AICoder/models/gguf/*.gguf

# 변경 후
python -m venv venv
GGUF 파일 위치: models/gguf/*.gguf (프로젝트 상대경로)
```

---

## 4단계: 모델 다운로드 (~4.4GB)

```bash
# Qwen2.5-Coder-7B-Instruct GGUF 모델 다운로드
# 저장 경로: d:/WP_AI_CODER/models/gguf/
cd d:/WP_AI_CODER
venv/Scripts/python.exe scripts/download_model.py
```

---

## 5단계: 서버 시작 및 확인

```bash
# 서버 시작 (포그라운드에서 직접 실행)
cd d:/WP_AI_CODER
venv/Scripts/python.exe scripts/api_server.py

# 또는 백그라운드 런처 사용
venv/Scripts/python.exe server.py

# 또는 PowerShell 스크립트 사용
.\start_server.ps1
```

---

## 6단계: 서버 동작 확인

```bash
# 헬스체크
curl http://localhost:8888/health
# 기대 결과: {"status":"ok","model":"qwen2.5-coder-7b-instruct-q4_k_m.gguf"}

# 대시보드 접속
# 브라우저에서 http://localhost:8888 열기

# API 테스트 (코드 생성 요청)
curl -X POST http://localhost:8888/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello World를 출력하는 C 코드를 작성해줘"}'

# 채팅 API 테스트
curl -X POST http://localhost:8888/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "C 언어로 버블 정렬 구현해줘"}]}'

# 통계 확인
curl http://localhost:8888/stats
```

---

## 7단계: 서버 종료

```bash
# PowerShell 스크립트 사용
.\stop_server.ps1

# 또는 수동으로 (server.pid 파일에서 PID 확인 후)
# taskkill /PID <pid> /F
```

---

## 설치 결과 요약

| 항목 | 상태 | 비고 |
|------|------|------|
| Python 3.13 venv | ✅ 완료 | d:/WP_AI_CODER/venv/ |
| pip 업그레이드 | ✅ 완료 | pip 26.0.1 |
| requirements.txt 설치 | ⏳ 진행중 | llama-cpp-python C++ 빌드 중 |
| 경로 수정 (6개 파일) | ✅ 완료 | 하드코딩 → 상대경로 |
| 모델 다운로드 | ⏳ 대기 | pip 완료 후 진행 |
| 서버 기동 확인 | ⏳ 대기 | 모델 다운로드 후 진행 |
| 헬스체크 통과 | ⏳ 대기 | - |
| API 테스트 통과 | ⏳ 대기 | - |

---

## 트러블슈팅

### llama-cpp-python 빌드 실패 시

```bash
# 사전 빌드된 wheel 사용 (CPU 전용)
venv/Scripts/pip.exe install llama-cpp-python --prefer-binary

# 그래도 실패하면 특정 버전 지정
venv/Scripts/pip.exe install llama-cpp-python==0.2.90 --prefer-binary
```

### 모델 경로 확인

```bash
# 모델이 올바른 위치에 있는지 확인
ls d:/WP_AI_CODER/models/gguf/*.gguf
```

### 포트 충돌 시

```bash
# 8888 포트 사용 중인 프로세스 확인
netstat -ano | findstr :8888
```
