"""하네스 설정 — 에이전트 동작 파라미터"""
import os
import json

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "harness_config.json")

DEFAULT_CONFIG = {
    # 에이전트 루프
    "max_iterations": 15,
    "temperature": 0.1,
    "max_tokens": 1024,

    # 컨텍스트 관리
    "max_turns": 10,
    "max_context_chars": 8000,

    # 도구 제한
    "command_timeout": 30,
    "max_file_read_lines": 200,
    "max_search_results": 30,

    # 안전장치
    "confirm_before_write": True,
    "confirm_before_command": False,
    "blocked_paths": [
        "/etc", "/usr", "/bin", "/sbin",
        "C:\\Windows", "C:\\Program Files",
    ],
}


def load_config() -> dict:
    """설정 파일 로드. 없으면 기본값 사용."""
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
    """설정 파일 저장."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
