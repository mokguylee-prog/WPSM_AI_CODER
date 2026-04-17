"""환경 검증 스크립트"""
import sys
import os

print(f"Python: {sys.version}")
print(f"플랫폼: {sys.platform}")

# llama-cpp-python
try:
    from llama_cpp import Llama
    print("llama-cpp-python: OK")
except ImportError:
    print("llama-cpp-python: 미설치 → pip install llama-cpp-python")

# fastapi
try:
    import fastapi
    print(f"FastAPI: {fastapi.__version__}")
except ImportError:
    print("FastAPI: 미설치 → pip install fastapi uvicorn")

# requests
try:
    import requests
    print(f"requests: {requests.__version__}")
except ImportError:
    print("requests: 미설치")

# 모델 파일 확인
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Sm_AICoder", "models", "gguf")
if os.path.isdir(MODEL_DIR):
    files = [f for f in os.listdir(MODEL_DIR) if f.endswith(".gguf")]
    if files:
        for f in files:
            size_gb = os.path.getsize(os.path.join(MODEL_DIR, f)) / 1024**3
            print(f"모델 발견: {f} ({size_gb:.1f} GB)")
    else:
        print(f"모델 없음: {MODEL_DIR}에 .gguf 파일이 없습니다")
        print("→ python scripts/download_model.py 로 다운로드하세요")
else:
    print(f"모델 디렉토리 없음: {MODEL_DIR}")
    print("→ python scripts/download_model.py 로 다운로드하세요")
