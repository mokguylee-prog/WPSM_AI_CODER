# Windows 전용 설정

## Python 경로 설정

여러 버전의 Python이 설치된 경우, 호환되는 버전(3.10~3.13)으로 venv를 생성해야 합니다.

```powershell
# 설치된 Python 확인
where python

# 특정 버전으로 venv 생성 (예: 3.13)
$py = "C:\Users\<username>\AppData\Local\Programs\Python\Python313\python.exe"
& $py -m venv venv
```

> Python 3.14는 llama-cpp-python 호환이 확인되지 않았습니다. 3.13 이하를 사용하세요.

---

## llama-cpp-python MSVC 빌드 문제

최신 llama-cpp-python은 MSVC 컴파일러에서 유니코드 인코딩 에러가 발생할 수 있습니다.

```text
error C2001: 새 줄 바꿈 문자가 상수에 있습니다
```

**해결 방법:**

```powershell
# 0.3.8 버전으로 설치 (MSVC 인코딩 이슈 없음)
venv\Scripts\pip.exe install llama-cpp-python==0.3.8 --prefer-binary
```

---

## HuggingFace 캐시 경로 변경

기본 캐시가 C 드라이브에 저장됩니다. D 드라이브로 변경하려면:

```powershell
# 시스템 환경변수 설정
[Environment]::SetEnvironmentVariable("HF_HOME", "D:\models\huggingface", "User")
```

또는 Python에서:

```python
import os
os.environ["HF_HOME"] = "D:/models/huggingface"
```

---

## 방화벽 / 프록시 설정

회사 네트워크에서 HuggingFace 접속이 안 될 때:

```python
import os
os.environ["HTTPS_PROXY"] = "http://proxy.company.com:8080"
os.environ["HTTP_PROXY"] = "http://proxy.company.com:8080"
```

또는 오프라인 모드 (모델 파일을 수동으로 복사한 경우):

```python
os.environ["HF_HUB_OFFLINE"] = "1"
```

---

## 가상 메모리 설정

7B 모델 로딩 시 물리 RAM이 부족하면 가상 메모리를 늘려야 합니다.

1. `제어판` → `시스템` → `고급 시스템 설정`
2. `성능` → `설정` → `고급` → `가상 메모리 변경`
3. 사용자 지정 크기: 초기 크기 16384 MB, 최대 크기 32768 MB

> 8GB RAM에서 7B 모델을 사용하는 경우 가상 메모리 설정을 권장합니다.

---

## 경로 처리

Windows에서 Python 경로 처리 시 `pathlib.Path`를 사용하면 안전합니다.

```python
from pathlib import Path

model_path = Path("Sm_AICoder/models/gguf")
for gguf in model_path.glob("*.gguf"):
    print(gguf.name)
```

---

## 포트 충돌 확인

서버 시작 시 `8888` 포트가 이미 사용 중이면:

```powershell
netstat -ano | findstr :8888
# PID 확인 후 종료
taskkill /PID <pid> /F
```

---

## GPU 가속 (선택사항)

NVIDIA GPU가 있는 경우 CUDA를 설정하면 추론 속도를 크게 높일 수 있습니다.

### NVIDIA 드라이버 확인

```powershell
nvidia-smi
```

### CUDA 환경변수

```text
CUDA_HOME = C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1
Path += C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin
```

### llama-cpp-python GPU 빌드

```powershell
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121
```

### server/scripts/api_server.py에서 GPU 레이어 설정

```python
N_GPU_LAYERS = 33  # 기본값 0 (CPU 전용) → 원하는 레이어 수로 변경
```
