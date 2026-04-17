"""파일 관련 도구 — read_file, list_files, write_file"""
from __future__ import annotations
import os
import fnmatch
from harness.tools.registry import TOOL_REGISTRY


def read_file(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """파일을 읽어 내용을 반환. 줄 번호 포함."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"파일 없음: {path}")

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    total = len(lines)
    if start_line < 0:
        start_line = 0
    if end_line <= 0 or end_line > total:
        end_line = total
    # 큰 파일 보호: 최대 200줄
    if end_line - start_line > 200:
        end_line = start_line + 200

    selected = lines[start_line:end_line]
    numbered = []
    for i, line in enumerate(selected, start=start_line + 1):
        numbered.append(f"{i:>4} | {line.rstrip()}")

    header = f"[{os.path.basename(path)}] 줄 {start_line+1}-{end_line}/{total}"
    return header + "\n" + "\n".join(numbered)


def list_files(path: str = ".", pattern: str = "*", max_depth: int = 3) -> str:
    """디렉토리 트리를 반환. glob 패턴 필터 지원."""
    if not os.path.isdir(path):
        raise NotADirectoryError(f"디렉토리 없음: {path}")

    results = []
    base = os.path.abspath(path)

    for root, dirs, files in os.walk(base):
        depth = root.replace(base, "").count(os.sep)
        if depth >= max_depth:
            dirs.clear()
            continue

        # 숨김 폴더, venv, __pycache__, .git, node_modules 제외
        dirs[:] = [
            d for d in sorted(dirs)
            if not d.startswith(".")
            and d not in ("venv", "__pycache__", "node_modules", ".git")
        ]

        rel = os.path.relpath(root, base)
        indent = "  " * depth
        if rel != ".":
            results.append(f"{indent}{rel}/")

        for f in sorted(files):
            if fnmatch.fnmatch(f, pattern):
                results.append(f"{indent}  {f}")

    if not results:
        return f"(패턴 '{pattern}'에 맞는 파일 없음)"
    return "\n".join(results[:200])  # 최대 200줄


def write_file(path: str, content: str) -> str:
    """파일 전체를 작성. 새 파일 생성 전용 — 기존 파일은 apply_patch 사용 권장."""
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return f"파일 작성 완료: {path} ({len(content)} bytes)"


# ── 레지스트리 등록 ──
TOOL_REGISTRY.register(
    name="read_file",
    func=read_file,
    description="파일을 읽어 줄 번호와 함께 내용을 반환합니다. 큰 파일은 범위를 지정하세요.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "읽을 파일 경로"},
            "start_line": {"type": "integer", "description": "시작 줄 (0-based, 기본 0)", "default": 0},
            "end_line": {"type": "integer", "description": "끝 줄 (0이면 끝까지)", "default": 0},
        },
        "required": ["path"],
    },
)

TOOL_REGISTRY.register(
    name="list_files",
    func=list_files,
    description="디렉토리 트리를 반환합니다. 패턴으로 필터링 가능합니다.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "탐색할 디렉토리 경로", "default": "."},
            "pattern": {"type": "string", "description": "glob 패턴 (예: *.py)", "default": "*"},
            "max_depth": {"type": "integer", "description": "최대 깊이 (기본 3)", "default": 3},
        },
        "required": [],
    },
)

TOOL_REGISTRY.register(
    name="write_file",
    func=write_file,
    description="새 파일을 작성합니다. 기존 파일 수정은 apply_patch를 사용하세요.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "작성할 파일 경로"},
            "content": {"type": "string", "description": "파일 내용"},
        },
        "required": ["path", "content"],
    },
)
