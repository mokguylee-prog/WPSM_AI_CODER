"""File tools: read_file, list_files, write_file."""
from __future__ import annotations

import os
import fnmatch
from Sm_AIAgent.tools.registry import TOOL_REGISTRY


def read_file(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """Read a file and return numbered lines."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    total = len(lines)
    if start_line < 0:
        start_line = 0
    if end_line <= 0 or end_line > total:
        end_line = total
    if end_line - start_line > 200:
        end_line = start_line + 200

    selected = lines[start_line:end_line]
    numbered = [f"{i:>4} | {line.rstrip()}" for i, line in enumerate(selected, start=start_line + 1)]

    header = f"[{os.path.basename(path)}] lines {start_line + 1}-{end_line}/{total}"
    return header + "\n" + "\n".join(numbered)


def list_files(path: str = ".", pattern: str = "*", max_depth: int = 3) -> str:
    """Return a directory tree with optional glob filter."""
    if not os.path.isdir(path):
        raise NotADirectoryError(f"Directory not found: {path}")

    results = []
    base = os.path.abspath(path)

    for root, dirs, files in os.walk(base):
        depth = root.replace(base, "").count(os.sep)
        if depth >= max_depth:
            dirs.clear()
            continue

        dirs[:] = [
            d
            for d in sorted(dirs)
            if not d.startswith(".") and d not in ("venv", "__pycache__", "node_modules", ".git")
        ]

        rel = os.path.relpath(root, base)
        indent = "  " * depth
        if rel != ".":
            results.append(f"{indent}{rel}/")

        for f in sorted(files):
            if fnmatch.fnmatch(f, pattern):
                results.append(f"{indent}  {f}")

    if not results:
        return f"(No files matched pattern: {pattern})"
    return "\n".join(results[:200])


def write_file(path: str, content: str) -> str:
    """Write entire file content (create if missing)."""
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return f"File written: {path} ({len(content)} bytes)"


TOOL_REGISTRY.register(
    name="read_file",
    func=read_file,
    description="Read a file and return numbered lines.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to read"},
            "start_line": {"type": "integer", "description": "Start line (0-based)", "default": 0},
            "end_line": {"type": "integer", "description": "End line (0 means EOF)", "default": 0},
        },
        "required": ["path"],
    },
)

TOOL_REGISTRY.register(
    name="list_files",
    func=list_files,
    description="List files in a directory tree.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path", "default": "."},
            "pattern": {"type": "string", "description": "Glob pattern (e.g. *.py)", "default": "*"},
            "max_depth": {"type": "integer", "description": "Max traversal depth", "default": 3},
        },
        "required": [],
    },
)

TOOL_REGISTRY.register(
    name="write_file",
    func=write_file,
    description="Write a full file content.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Output file path"},
            "content": {"type": "string", "description": "File content"},
        },
        "required": ["path", "content"],
    },
)
