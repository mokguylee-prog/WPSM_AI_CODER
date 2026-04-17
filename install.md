# WP_AI_CODER 서버 설치 기록

> 설치 일시: 2026-04-17
> 설치 환경: Windows 11 Pro, Python 3.13, MSVC 19.44 (VS 2022)

---

## 1단계: 환경 확인

```bash
# Python 버전 확인
python --version
# 결과: Python 3.14.3

# 사용 가능한 Python 경로 확인
where python
# 결과:
#   C:\Python314\python.exe
#   C:\Users\kadelee\AppData\Local\Programs\Python\Python313\python.exe
#   C:\Users\kadelee\AppData\Local\Microsoft\WindowsApps\python.exe

# 기존 환경 확인 (모두 없음)
ls D:/Sm_AICoder/venv/Scripts/python.exe   # -> 없음 (D:/Sm_AICoder 자체가 없음)
ls D:/Sm_AICoder/models/gguf/*.gguf        # -> 없음
pip list | grep -iE "llama|fastapi|uvicorn|pydantic"  # -> 미설치
```

---

## 2단계: 가상환경 생성 (Python 3.13)

```bash
cd d:/WP_AI_CODER

# Python 3.14는 llama-cpp-python과 호환 문제 가능성이 있어 3.13 사용
"C:/Users/kadelee/AppData/Local/Programs/Python/Python313/python.exe" -m venv venv

# pip 업그레이드
venv/Scripts/python.exe -m pip install --upgrade pip
# 결과: pip 25.3 -> 26.0.1 업그레이드 완료
```

---

## 3단계: 의존성 설치

### 3-1. 첫 번째 시도 (실패)

```bash
venv/Scripts/pip.exe install -r requirements.txt
```

**결과: llama-cpp-python 최신 버전 빌드 실패**

원인: llama.cpp 소스의 `jinja/utils.h` 파일에 비ASCII(유니코드) 문자가 있어
MSVC 컴파일러가 인코딩 에러 발생 (`error C2001: 새 줄 바꿈 문자가 상수에 있습니다`)

### 3-2. 해결: llama-cpp-python 0.3.8 버전 지정 설치

```bash
# 0.3.8 버전은 해당 유니코드 이슈 없이 MSVC에서 정상 빌드됨
venv/Scripts/pip.exe install llama-cpp-python==0.3.8 --prefer-binary
# 결과: 빌드 성공, llama_cpp_python-0.3.8-cp313-cp313-win_amd64.whl

# 나머지 패키지 설치
venv/Scripts/pip.exe install fastapi uvicorn pydantic requests huggingface_hub
# 결과: 전부 설치 완료
```

### 설치된 주요 패키지 목록

| 패키지 | 버전 |
|--------|------|
| llama-cpp-python | 0.3.8 |
| fastapi | 0.136.0 |
| uvicorn | 0.44.0 |
| pydantic | 2.13.2 |
| requests | 2.33.1 |
| huggingface_hub | 1.11.0 |

---

## 4단계: 경로 수정 (D:/Sm_AICoder -> 프로젝트 상대경로)

원래 코드가 `D:/Sm_AICoder`으로 하드코딩되어 있어 현재 위치(`D:/WP_AI_CODER`)에서 동작하도록 수정함.

### 수정된 파일 목록

**scripts/api_server.py**
```python
# 변경 전
MODEL_DIR = "D:/Sm_AICoder/models/gguf"
LOG_DIR   = "logs"

# 변경 후
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR  = os.path.join(BASE_DIR, "models", "gguf")
LOG_DIR    = os.path.join(BASE_DIR, "logs")
```

**scripts/download_model.py**
```python
# 변경 전
SAVE_DIR = "D:/Sm_AICoder/models/gguf"

# 변경 후
SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "gguf")
```

**start_server.ps1 / start_gui.ps1 / start_client.ps1 / build_client.ps1**
```powershell
# 변경 전
$venv = "D:\Sm_AICoder\venv\Scripts\python.exe"
if (-not (Test-Path $venv)) { $venv = "python" }

# 변경 후
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $scriptDir "venv\Scripts\python.exe"
if (-not (Test-Path $venv)) { $venv = "python" }
```

**CLAUDE.md**
```
# 변경 전
python -m venv D:\Sm_AICoder\venv
GGUF 파일 위치: D:/Sm_AICoder/models/gguf/*.gguf

# 변경 후
python -m venv venv
GGUF 파일 위치: models/gguf/*.gguf (프로젝트 상대경로)
```

---

## 5단계: 모델 다운로드 (~4.4GB)

```bash
cd d:/WP_AI_CODER
venv/Scripts/python.exe scripts/download_model.py
# 모델: Qwen2.5-Coder-7B-Instruct Q4_K_M
# 저장 위치: d:/WP_AI_CODER/models/gguf/qwen2.5-coder-7b-instruct-q4_k_m.gguf
# 용량: ~4.4GB, ��운로드 시간: 네트워크에 따라 5~30분
```

---

## 6단계: 서버 시작

```bash
cd d:/WP_AI_CODER

# 방법 1: 포그라운드에서 직접 실행
venv/Scripts/python.exe scripts/api_server.py

# 방법 2: 백그라운드 런처 사용 (PID 관리)
venv/Scripts/python.exe server.py

# 방법 3: PowerShell 스크립트
.\start_server.ps1
```

---

## 7단계: 서버 동작 확인

```bash
# 헬스체크
curl http://localhost:8888/health
# 기대 결과: {"status":"ok","model":"qwen2.5-coder-7b-instruct-q4_k_m.gguf"}

# 대시보드 접속 (브라우저)
# http://localhost:8888

# 코드 생성 API 테스트
curl -X POST http://localhost:8888/generate -H "Content-Type: application/json" -d "{\"prompt\": \"Hello World를 출력하는 C 코드를 작성해줘\"}"

# 채팅 API 테스트
curl -X POST http://localhost:8888/chat -H "Content-Type: application/json" -d "{\"messages\": [{\"role\": \"user\", \"content\": \"C 언어로 버블 정렬 구현해줘\"}]}"

# 통계 확인
curl http://localhost:8888/stats
```

---

## 8단계: 서버 종료

```bash
# PowerShell 스크립트 사용
.\stop_server.ps1

# 또는 수동으로
# server.pid 파일에서 PID 확인 후: taskkill /PID <pid> /F
```

---

## 설치 결과 요약

| 항목 | 상태 | 비고 |
|------|------|------|
| Python 3.13 venv 생성 | OK | d:/WP_AI_CODER/venv/ |
| pip 업그레이드 | OK | pip 26.0.1 |
| llama-cpp-python 설치 | OK | 0.3.8 (최신은 MSVC 인코딩 에러) |
| fastapi/uvicorn 등 설치 | OK | 전부 완료 |
| 경로 수정 (6개 파일) | OK | D:/Sm_AICoder -> 상대경로 |
| 모델 다운로드 | OK | qwen2.5-coder-7b-instruct-q4_k_m.gguf (4.4GB) |
| 서버 기동 | OK | http://localhost:8888 |
| 헬스체크 통과 | OK | {"status":"ok","model":"..."} |
| /generate API | OK | Hello World C 코드 생성 확인 |
| /chat API | OK | 버블 정렬 코드 생성 확인 |
| /stats API | OK | 요청 통계 정상 반환 |

---

## 트러블슈���

### llama-cpp-python 최신 버전 빌드 실패 시
```bash
# 0.3.8 버전으로 설치 (MSVC 인코딩 이슈 회피)
venv/Scripts/pip.exe install llama-cpp-python==0.3.8 --prefer-binary
```

### 모델 경로 확인
```bash
ls d:/WP_AI_CODER/models/gguf/*.gguf
```

### 포트 충돌 시
```bash
netstat -ano | findstr :8888
```

### 서버 로그 확인
```bash
cat server_out.log   # 표준 출력
cat server_err.log   # 에러 출력
```
