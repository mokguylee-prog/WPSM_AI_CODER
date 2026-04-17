"""명령 실행 도구 — run_command (화이트리스트 기반 안전 실행)"""
from __future__ import annotations
import subprocess
import shlex
from harness.tools.registry import TOOL_REGISTRY


# 허용된 명령어 화이트리스트 (접두사 매칭)
ALLOWED_COMMANDS = [
    "python", "py",
    "pip", "pip3",
    "git status", "git diff", "git log", "git branch", "git show",
    "dir", "ls", "cat", "type", "head", "tail",
    "gcc", "g++", "cl", "make", "cmake",
    "pytest", "python -m pytest", "python -m unittest",
    "node", "npm test", "npx",
    "cargo test", "cargo build", "cargo check",
    "go test", "go build", "go vet",
    "echo", "pwd", "whoami",
]

# 절대 금지 명령어 (이것들이 포함되면 차단)
BLOCKED_PATTERNS = [
    "rm -rf", "del /s", "format", "mkfs",
    "shutdown", "reboot", "halt",
    ":(){ :|:& };:",  # fork bomb
    "> /dev/sda", "dd if=",
    "curl | sh", "wget | sh", "curl | bash", "wget | bash",
    "powershell -enc", "powershell -e ",
]


def run_command(command: str, timeout: int = 30) -> str:
    """허용된 명령어만 실행합니다. 위험한 명령은 차단됩니다."""
    cmd_lower = command.strip().lower()

    # 금지 패턴 확인
    for blocked in BLOCKED_PATTERNS:
        if blocked in cmd_lower:
            raise PermissionError(f"차단된 명령어 패턴: {blocked}")

    # 화이트리스트 확인
    allowed = False
    for prefix in ALLOWED_COMMANDS:
        if cmd_lower.startswith(prefix.lower()):
            allowed = True
            break

    if not allowed:
        raise PermissionError(
            f"허용되지 않은 명령어: {command}\n"
            f"허용 목록: {', '.join(ALLOWED_COMMANDS[:10])}..."
        )

    # 타임아웃 제한
    timeout = min(max(timeout, 5), 60)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=".",
        )

        output_parts = []
        if result.stdout.strip():
            stdout = result.stdout.strip()
            if len(stdout) > 3000:
                stdout = stdout[:3000] + "\n... (출력 생략됨)"
            output_parts.append(f"[stdout]\n{stdout}")

        if result.stderr.strip():
            stderr = result.stderr.strip()
            if len(stderr) > 1500:
                stderr = stderr[:1500] + "\n... (에러 출력 생략됨)"
            output_parts.append(f"[stderr]\n{stderr}")

        if result.returncode != 0:
            output_parts.append(f"[exit code: {result.returncode}]")

        return "\n".join(output_parts) if output_parts else "(출력 없음)"

    except subprocess.TimeoutExpired:
        return f"[시간 초과: {timeout}초]"


# ── 레지스트리 등록 ──
TOOL_REGISTRY.register(
    name="run_command",
    func=run_command,
    description=(
        "쉘 명령을 실행합니다. 안전을 위해 화이트리스트 기반입니다. "
        "허용: python, git status/diff/log, pytest, gcc/g++, make 등"
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "실행할 명령어"},
            "timeout": {"type": "integer", "description": "타임아웃(초), 최대 60", "default": 30},
        },
        "required": ["command"],
    },
)
