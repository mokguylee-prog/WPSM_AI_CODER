# Windows 전용 설정

## CUDA 환경 구성

### 1. NVIDIA 드라이버 확인

```powershell
nvidia-smi
```

출력 예시:
```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 546.33    Driver Version: 546.33    CUDA Version: 12.3          |
+-----------------------------------------------------------------------------+
| GPU  Name            TCC/WDDM | Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|        Memory-Usage | GPU-Util  Compute M. |
|   0  NVIDIA GeForce RTX 4090  | 00000000:01:00.0 On |                  N/A |
+-----------------------------------------------------------------------------+
```

### 2. CUDA 경로 환경변수 설정

`시스템 환경변수`에 추가:
```
CUDA_HOME = C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1
Path += C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin
Path += C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\libnvvp
```

---

## HuggingFace 캐시 경로 변경

기본 캐시가 C 드라이브에 저장됨. D 드라이브로 변경:

```powershell
# 시스템 환경변수 설정
[Environment]::SetEnvironmentVariable("HF_HOME", "D:\models\huggingface", "User")
[Environment]::SetEnvironmentVariable("TRANSFORMERS_CACHE", "D:\models\huggingface\hub", "User")
```

또는 Python에서:
```python
import os
os.environ["HF_HOME"] = "D:/models/huggingface"
```

---

## WSL2 사용 (bitsandbytes 문제 해결)

bitsandbytes가 Windows에서 설치되지 않을 때:

```powershell
# WSL2 설치
wsl --install

# Ubuntu 실행
wsl

# WSL2 내에서
pip install torch transformers accelerate bitsandbytes
python /mnt/d/work_web/StarCoder/scripts/generate_4bit.py
```

---

## 메모리 최적화

```python
import torch
import gc

# GPU 메모리 정리
def clear_gpu_memory():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

# 사용 후 정리
del model
clear_gpu_memory()
```

---

## 가상 메모리 설정

대형 모델 로딩 시 시스템 RAM이 부족할 경우:

1. `제어판` → `시스템` → `고급 시스템 설정`
2. `성능` → `설정` → `고급` → `가상 메모리 변경`
3. 사용자 지정 크기: 초기 크기 32768 MB, 최대 크기 65536 MB

---

## 경로 처리 (슬래시)

```python
from pathlib import Path

# Windows에서도 안전하게 경로 처리
model_path = Path("D:/models/starcoder2-7b")
cache_dir = Path("D:/models/cache")

model = AutoModelForCausalLM.from_pretrained(
    str(model_path),
    cache_dir=str(cache_dir)
)
```

---

## 방화벽 / 프록시 설정

회사 네트워크에서 HuggingFace 접속이 안 될 때:

```python
import os
os.environ["HTTPS_PROXY"] = "http://proxy.company.com:8080"
os.environ["HTTP_PROXY"] = "http://proxy.company.com:8080"
```

또는 오프라인 모드:
```python
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"
```
