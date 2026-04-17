"""GGUF 모델 다운로드 스크립트 (HuggingFace Hub)"""
from huggingface_hub import hf_hub_download
import os

# ── 설정 ──────────────────────────────────────────
# CPU에서 쓸 수 있는 instruction-following 코드 모델들
MODELS = {
    "qwen2.5-coder-7b": {
        "repo": "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
        "file": "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
        "desc": "Qwen2.5-Coder 7B (권장, ~4.4GB)",
    },
    "qwen2.5-coder-1.5b": {
        "repo": "Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
        "file": "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        "desc": "Qwen2.5-Coder 1.5B (경량, ~1.0GB)",
    },
    "deepseek-coder-6.7b": {
        "repo": "TheBloke/deepseek-coder-6.7B-instruct-GGUF",
        "file": "deepseek-coder-6.7b-instruct.Q4_K_M.gguf",
        "desc": "DeepSeek-Coder 6.7B (~3.8GB)",
    },
}

SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Sm_AICoder", "models", "gguf")
DEFAULT_MODEL = "qwen2.5-coder-7b"


def download(model_key: str = DEFAULT_MODEL):
    info = MODELS[model_key]
    os.makedirs(SAVE_DIR, exist_ok=True)
    dest = os.path.join(SAVE_DIR, info["file"])

    if os.path.exists(dest):
        print(f"이미 존재: {dest}")
        return dest

    print(f"다운로드: {info['desc']}")
    print(f"저장 위치: {dest}")
    path = hf_hub_download(
        repo_id=info["repo"],
        filename=info["file"],
        local_dir=SAVE_DIR,
    )
    print(f"완료: {path}")
    return path


if __name__ == "__main__":
    import sys

    print("사용 가능한 모델:")
    for k, v in MODELS.items():
        print(f"  {k:30s} : {v['desc']}")
    print()

    key = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    if key not in MODELS:
        print(f"알 수 없는 모델: {key}")
        sys.exit(1)

    download(key)
