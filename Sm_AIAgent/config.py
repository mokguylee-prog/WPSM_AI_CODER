"""Configuration for Sm_AIAgent."""
import os
import json

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "Sm_AIAgent_config.json")

DEFAULT_CONFIG = {
    "max_iterations": 15,
    "temperature": 0.1,
    "max_tokens": 1024,
    "max_turns": 10,
    "max_context_chars": 8000,
    "command_timeout": 30,
    "max_file_read_lines": 200,
    "max_search_results": 30,
    "confirm_before_write": True,
    "confirm_before_command": False,
    "blocked_paths": [
        "/etc",
        "/usr",
        "/bin",
        "/sbin",
        "C:\\Windows",
        "C:\\Program Files",
    ],
    # P5-2: 모델 라우팅
    #   first    — 첫 번째 사용자 턴에 사용할 모델 파일명 패턴 (큰 모델)
    #   followup — 후속 도구 호출 턴에 사용할 모델 파일명 패턴 (작은 모델)
    #   패턴은 파일명에 포함된 문자열을 대소문자 무시로 매칭한다.
    #   None 으로 설정하면 단일 모델 모드(라우팅 비활성화).
    "model_route": {
        "first": "qwen2.5-coder-7b",
        "followup": "qwen2.5-coder-1.5b",
    },
}


def load_config() -> dict:
    """Load config file and merge with defaults."""
    config = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            config.update(user_config)
        except Exception:
            pass
    return config


def save_config(config: dict):
    """Save full config to disk."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
