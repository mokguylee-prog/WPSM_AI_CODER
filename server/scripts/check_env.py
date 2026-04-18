"""Environment validation helper for the Sm_AICoder server stack."""
import os
import sys
import subprocess


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

# P5-1: GPU / CUDA 감지 상태 출력
print()
print("--- GPU / CUDA detection (P5-1) ---")
_cuda_found = False

try:
    import torch
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
        print(f"torch.cuda: OK  ->  {gpu_name} ({vram_gb:.1f} GB VRAM)")
        print("N_GPU_LAYERS will be set to: -1 (full offload)")
        _cuda_found = True
    else:
        print("torch.cuda: installed but no CUDA GPU detected")
except ImportError:
    print("torch: not installed (optional — used for CUDA detection only)")

if not _cuda_found:
    _smi_paths = [
        "nvidia-smi",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        r"C:\Windows\System32\nvidia-smi.exe",
    ]
    for _smi in _smi_paths:
        try:
            r = subprocess.run(
                [_smi, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout:
                try:
                    out = r.stdout.decode("utf-8").strip()
                except UnicodeDecodeError:
                    out = r.stdout.decode("cp949", errors="replace").strip()
                if out:
                    print(f"nvidia-smi: OK  ->  {out.splitlines()[0]}")
                    print("N_GPU_LAYERS will be set to: -1 (full offload)")
                    _cuda_found = True
                    break
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue

if not _cuda_found:
    print("No GPU detected. N_GPU_LAYERS will be set to: 0 (CPU-only)")

# P5-1: 환경변수 오버라이드 안내
env_layers = os.environ.get("N_GPU_LAYERS")
if env_layers is not None:
    print(f"N_GPU_LAYERS env override active: {env_layers}")
else:
    print("Tip: set env N_GPU_LAYERS=<n> to override auto-detect")

# P5-2: 모델 라우팅 상태
print()
print("--- Model routing (P5-2) ---")
print(f"MODEL_ROUTE_FIRST   (env): {os.environ.get('MODEL_ROUTE_FIRST', 'qwen2.5-coder-7b  (default)')}")
print(f"MODEL_ROUTE_FOLLOWUP (env): {os.environ.get('MODEL_ROUTE_FOLLOWUP', 'qwen2.5-coder-1.5b  (default)')}")

# P5-3: cache_prompt 상태
print()
print("--- Prompt cache (P5-3) ---")
cache_val = os.environ.get("CACHE_PROMPT", "1")
cache_enabled = cache_val.strip().lower() not in ("0", "false", "no")
print(f"CACHE_PROMPT env flag: {'enabled' if cache_enabled else 'disabled'} (not passed to llama-cpp)")

# 모델 파일 목록
print()
print("--- GGUF models ---")
if os.path.isdir(MODEL_DIR):
    files = [f for f in os.listdir(MODEL_DIR) if f.endswith(".gguf")]
    if files:
        for filename in sorted(files):
            size_gb = os.path.getsize(os.path.join(MODEL_DIR, filename)) / 1024 ** 3
            print(f"  {filename} ({size_gb:.1f} GB)")
        if len(files) == 1:
            print("  Note: only one model found. Routing will use it for both turns.")
            print("  -> python server/scripts/download_model.py qwen2.5-coder-1.5b")
    else:
        print(f"No GGUF model found in: {MODEL_DIR}")
        print("-> python server/scripts/download_model.py")
else:
    print(f"Model directory not found: {MODEL_DIR}")
    print("-> python server/scripts/download_model.py")
