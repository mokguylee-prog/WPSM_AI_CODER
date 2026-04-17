"""Command tool with allowlist-based execution."""
from __future__ import annotations

import subprocess
from Sm_AIAgent.tools.registry import TOOL_REGISTRY


ALLOWED_COMMANDS = [
    "python",
    "py",
    "pip",
    "pip3",
    "git status",
    "git diff",
    "git log",
    "git branch",
    "git show",
    "dir",
    "ls",
    "cat",
    "type",
    "head",
    "tail",
    "gcc",
    "g++",
    "cl",
    "make",
    "cmake",
    "pytest",
    "python -m pytest",
    "python -m unittest",
    "node",
    "npm test",
    "npx",
    "cargo test",
    "cargo build",
    "cargo check",
    "go test",
    "go build",
    "go vet",
    "echo",
    "pwd",
    "whoami",
]

BLOCKED_PATTERNS = [
    "rm -rf",
    "del /s",
    "format",
    "mkfs",
    "shutdown",
    "reboot",
    "halt",
    ":(){ :|:& };:",
    "> /dev/sda",
    "dd if=",
    "curl | sh",
    "wget | sh",
    "curl | bash",
    "wget | bash",
    "powershell -enc",
    "powershell -e ",
]


def run_command(command: str, timeout: int = 30, allow_unsafe: bool = False) -> str:
    """Execute a command only when it passes allowlist/blocklist checks."""
    cmd_lower = command.strip().lower()

    for blocked in BLOCKED_PATTERNS:
        if blocked in cmd_lower:
            raise PermissionError(f"Blocked command pattern: {blocked}")

    allowed = any(cmd_lower.startswith(prefix.lower()) for prefix in ALLOWED_COMMANDS)
    if not allowed and not allow_unsafe:
        suggestions = ", ".join(ALLOWED_COMMANDS[:12])
        raise PermissionError(
            f"Command is not allowed: {command}\n"
            f"Allowed prefixes: {suggestions}..."
        )

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
                stdout = stdout[:3000] + "\n... (stdout truncated)"
            output_parts.append(f"[stdout]\n{stdout}")

        if result.stderr.strip():
            stderr = result.stderr.strip()
            if len(stderr) > 1500:
                stderr = stderr[:1500] + "\n... (stderr truncated)"
            output_parts.append(f"[stderr]\n{stderr}")

        if result.returncode != 0:
            output_parts.append(f"[exit code: {result.returncode}]")

        return "\n".join(output_parts) if output_parts else "(no output)"

    except subprocess.TimeoutExpired:
        return f"[timeout: {timeout}s]"


TOOL_REGISTRY.register(
    name="run_command",
    func=run_command,
    description=(
        "Run shell command with allowlist safety checks. "
        "Examples: python, git status/diff/log, pytest, gcc/g++, make."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (max 60)", "default": 30},
            "allow_unsafe": {"type": "boolean", "description": "Bypass allowlist after explicit user approval", "default": False},
        },
        "required": ["command"],
    },
)
