"""Environment validation helper for the Sm_AICoder server stack."""
import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(SERVER_DIR)
MODEL_DIR = os.path.join(PROJECT_ROOT, "Sm_AICoder", "models", "gguf")


print(f"Python: {sys.version}")
print(f"Platform: {sys.platform}")

try:
    from llama_cpp import Llama  # noqa: F401
    print("llama-cpp-python: OK")
except ImportError:
    print("llama-cpp-python: missing -> pip install llama-cpp-python")

try:
    import fastapi
    print(f"FastAPI: {fastapi.__version__}")
except ImportError:
    print("FastAPI: missing -> pip install fastapi uvicorn")

try:
    import requests
    print(f"requests: {requests.__version__}")
except ImportError:
    print("requests: missing -> pip install requests")

if os.path.isdir(MODEL_DIR):
    files = [f for f in os.listdir(MODEL_DIR) if f.endswith(".gguf")]
    if files:
        for filename in files:
            size_gb = os.path.getsize(os.path.join(MODEL_DIR, filename)) / 1024 ** 3
            print(f"Model found: {filename} ({size_gb:.1f} GB)")
    else:
        print(f"No GGUF model found in: {MODEL_DIR}")
        print("-> python server/scripts/download_model.py")
else:
    print(f"Model directory not found: {MODEL_DIR}")
    print("-> python server/scripts/download_model.py")
