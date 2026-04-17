# 설치 가이드

> 기준 환경: Windows 11, Python 3.13, CPU 전용 실행

---

## 1. 준비 사항

- Python 3.10 이상 3.13 이하
- 여유 디스크 공간 6GB 이상
- RAM 8GB 이상
- PowerShell 실행 가능 환경

> Python 3.14는 `llama-cpp-python` 호환성이 불안정할 수 있어
> 권장하지 않습니다.

---

## 2. 가상환경 생성

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
```

특정 버전을 지정해야 하면 아래처럼 실행합니다.

```powershell
$py = "C:\Users\<username>\AppData\Local\Programs\Python\Python313\python.exe"
& $py -m venv venv
```

---

## 3. 패키지 설치

```powershell
venv\Scripts\pip.exe install -r requirements.txt
```

최신 `llama-cpp-python` 빌드에 문제가 있으면 다음처럼 설치합니다.

```powershell
venv\Scripts\pip.exe install llama-cpp-python==0.3.8 --prefer-binary
venv\Scripts\pip.exe install fastapi uvicorn pydantic requests huggingface_hub
```

---

## 4. 모델 다운로드

```powershell
venv\Scripts\python.exe server\scripts\download_model.py
```

- 기본 모델은 `Qwen2.5-Coder-7B-Instruct Q4_K_M` 입니다.
- 모델은 `Sm_AICoder/models/gguf/` 아래에 저장됩니다.
- 다운로드 크기는 약 4.4GB 입니다.

---

## 5. 서버 시작

```powershell
.\start_server.ps1
```

직접 실행하려면 아래 명령도 사용할 수 있습니다.

```powershell
venv\Scripts\python.exe server\server.py
venv\Scripts\python.exe server\scripts\api_server.py
```

---

## 6. 클라이언트 실행

```powershell
# GUI 클라이언트
.\start_gui.ps1

# CLI 클라이언트
.\start_client.ps1
```

웹 대시보드는 <http://localhost:8888> 에서 확인할 수 있습니다.

---

## 7. 설치 확인

```powershell
curl http://localhost:8888/health
```

정상 응답 예:

```json
{
  "status": "ok",
  "model": "qwen2.5-coder-7b-instruct-q4_k_m.gguf"
}
```

---

## 8. 선택 사항: D 드라이브 사용

모델과 캐시를 D 드라이브로 돌리고 싶다면 보조 스크립트를 사용합니다.

```powershell
.\venv\Scripts\powershell.exe -ExecutionPolicy Bypass `
  -File .\server\scripts\setup_d_drive.ps1
```

이 스크립트는 다음 작업을 수행합니다.

- Hugging Face 캐시와 pip 캐시를 D 드라이브로 이동
- 프로젝트 루트의 `venv`는 그대로 유지
- 필요 시 `Sm_AICoder/models/gguf`를 D 드라이브와 연결

---

## 9. 자주 쓰는 명령

| 목적 | 명령 |
| ---- | ---- |
| 환경 확인 | `venv\Scripts\python.exe server\scripts\check_env.py` |
| 모델 다운로드 | `venv\Scripts\python.exe server\scripts\download_model.py` |
| 서버 시작 | `.\start_server.ps1` |
| 서버 종료 | `.\stop_server.ps1` |
| GUI 실행 | `.\start_gui.ps1` |
| CLI 실행 | `.\start_client.ps1` |
| GUI EXE 빌드 | `.\build_client.ps1` |

---

## 10. 트러블슈팅

### 모델 파일이 없다는 오류

```text
GGUF 모델이 없습니다: .../Sm_AICoder/models/gguf
```

`server/scripts/download_model.py`를 먼저 실행하세요.

### 포트 8888이 이미 사용 중인 경우

```powershell
netstat -ano | findstr :8888
taskkill /PID <pid> /F
```

### 서버 로그를 확인하고 싶은 경우

```powershell
Get-Content server\server_out.log
Get-Content server\server_err.log
```
