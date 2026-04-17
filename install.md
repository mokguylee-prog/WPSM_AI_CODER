# WP_AI_CODER 설치 기록

> 설치 일시: 2026-04-17
> 설치 환경: Windows 11 Pro, Python 3.13, MSVC 19.44

---

## 1. 환경 확인

```powershell
python --version
where python
```

확인 결과:

- 시스템에는 Python 3.14.3과 Python 3.13이 함께 설치되어 있었습니다.
- `venv`와 GGUF 모델 파일은 아직 없는 상태였습니다.
- 핵심 패키지도 설치되지 않은 상태였습니다.

---

## 2. 가상환경 생성

`llama-cpp-python` 호환성을 고려해 Python 3.13으로 `venv`를 만들었습니다.

```powershell
cd d:\WP_AI_CODER
"C:\Users\kadelee\AppData\Local\Programs\Python\Python313\python.exe" -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
```

결과:

- 프로젝트용 `venv` 생성 완료
- `pip` 업그레이드 완료

---

## 3. 패키지 설치

처음에는 아래처럼 일반 설치를 시도했습니다.

```powershell
venv\Scripts\pip.exe install -r requirements.txt
```

최신 `llama-cpp-python`은 MSVC 환경에서 빌드 문제가 있었습니다.
그래서 `0.3.8` 버전으로 우회 설치했습니다.

```powershell
venv\Scripts\pip.exe install llama-cpp-python==0.3.8 --prefer-binary
venv\Scripts\pip.exe install fastapi uvicorn pydantic requests huggingface_hub
```

설치 확인 버전:

| 패키지 | 버전 |
| ------ | ---- |
| `llama-cpp-python` | `0.3.8` |
| `fastapi` | `0.136.0` |
| `uvicorn` | `0.44.0` |
| `pydantic` | `2.13.2` |
| `requests` | `2.33.1` |
| `huggingface_hub` | `1.11.0` |

---

## 4. 경로 정리

기존 코드에는 `D:/StarCoder3` 경로가 남아 있었습니다.
이를 현재 프로젝트 구조에 맞게 모두 정리했습니다.

### 수정 대상

- `server/scripts/api_server.py`
- `server/scripts/download_model.py`
- `start_server.ps1`
- `start_gui.ps1`
- `start_client.ps1`
- `build_client.ps1`
- `CLAUDE.md`

### 반영 내용

- 모델 경로를 `Sm_AICoder/models/gguf` 기준으로 변경
- 로그 경로를 `server/logs` 기준으로 정리
- 실행 스크립트가 루트 `venv`를 참조하도록 수정
- 문서도 현재 폴더 구조 기준으로 갱신

---

## 5. 모델 다운로드

```powershell
cd d:\WP_AI_CODER
venv\Scripts\python.exe server\scripts\download_model.py
```

결과:

- 모델: `Qwen2.5-Coder-7B-Instruct Q4_K_M`
- 저장 위치:
  `d:\WP_AI_CODER\Sm_AICoder\models\gguf\`
- 다운로드 크기: 약 4.4GB

---

## 6. 서버 시작

다음 세 가지 방식 모두 확인했습니다.

```powershell
venv\Scripts\python.exe server\scripts\api_server.py
venv\Scripts\python.exe server\server.py
.\start_server.ps1
```

이후 기본 사용 경로는 루트 스크립트로 정리했습니다.

---

## 7. 동작 확인

헬스체크와 주요 API를 확인했습니다.

```powershell
curl http://localhost:8888/health
curl http://localhost:8888/stats
```

추가로 아래 호출도 정상 동작을 확인했습니다.

```powershell
curl -X POST http://localhost:8888/generate `
  -H "Content-Type: application/json" `
  -d "{\"prompt\": \"Hello World를 출력하는 C 코드를 작성해줘\"}"

curl -X POST http://localhost:8888/chat `
  -H "Content-Type: application/json" `
  -d "{\"messages\": [{\"role\": \"user\", \"content\": \"C 언어로 버블 정렬 구현해줘\"}]}"
```

---

## 8. 서버 종료

```powershell
.\stop_server.ps1
```

필요하면 `server/server.pid`를 확인한 뒤
직접 `taskkill`로 종료할 수도 있습니다.

---

## 9. 최종 상태

| 항목 | 상태 | 비고 |
| ---- | ---- | ---- |
| Python 3.13 `venv` 생성 | 완료 | `d:\WP_AI_CODER\venv` |
| 패키지 설치 | 완료 | `llama-cpp-python==0.3.8` 사용 |
| 경로 정리 | 완료 | 구 하드코딩 경로 제거 |
| 모델 다운로드 | 완료 | `Sm_AICoder\models\gguf` |
| 서버 시작 | 완료 | `<http://localhost:8888>` |
| `/health` 확인 | 완료 | 정상 응답 |
| `/generate` 확인 | 완료 | 정상 응답 |
| `/chat` 확인 | 완료 | 정상 응답 |
| `/stats` 확인 | 완료 | 정상 응답 |

---

## 10. 트러블슈팅

### `llama-cpp-python` 빌드 실패 시

```powershell
venv\Scripts\pip.exe install llama-cpp-python==0.3.8 --prefer-binary
```

### 모델 위치 확인

```powershell
Get-ChildItem .\Sm_AICoder\models\gguf\*.gguf
```

### 포트 충돌 확인

```powershell
netstat -ano | findstr :8888
```

### 서버 로그 확인

```powershell
Get-Content .\server\server_out.log
Get-Content .\server\server_err.log
```
