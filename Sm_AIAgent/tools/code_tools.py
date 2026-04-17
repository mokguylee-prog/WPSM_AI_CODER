"""Code tools: search_code, apply_patch, show_diff."""
from __future__ import annotations

import os
import re
import subprocess
import difflib
from Sm_AIAgent.tools.registry import TOOL_REGISTRY


def search_code(query: str, path: str = ".", pattern: str = "*.py", max_results: int = 30) -> str:
    """Search text/regex across source files."""
    if not os.path.isdir(path):
        raise NotADirectoryError(f"Directory not found: {path}")

    results = []
    base = os.path.abspath(path)
    skip_dirs = {".git", "venv", "__pycache__", "node_modules", ".mypy_cache"}

    try:
        regex = re.compile(query, re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(query), re.IGNORECASE)

    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if not _match_pattern(fname, pattern):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if regex.search(line):
                            rel = os.path.relpath(fpath, base)
                            results.append(f"{rel}:{i}: {line.rstrip()}")
                            if len(results) >= max_results:
                                break
            except (PermissionError, OSError):
                continue
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break

    if not results:
        return f"(No matches for '{query}')"
    return f"search '{query}' results: {len(results)}\n" + "\n".join(results)


def apply_patch(path: str, old_string: str, new_string: str) -> str:
    """Replace exactly one occurrence in a file and return short diff."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        original = f.read()

    count = original.count(old_string)
    if count == 0:
        raise ValueError(
            f"old_string was not found in file.\n"
            f"file: {path}\n"
            f"old_string (first 100 chars): {old_string[:100]!r}"
        )
    if count > 1:
        raise ValueError(f"old_string matched {count} times. Provide a more specific string.")

    modified = original.replace(old_string, new_string, 1)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(modified)

    diff = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(path)}",
            tofile=f"b/{os.path.basename(path)}",
            lineterm="",
        )
    )
    diff_text = "\n".join(diff[:50]) if diff else "(No changes)"
    return f"Patch applied: {path}\n{diff_text}"


def show_diff(path: str = ".") -> str:
    """Return git diff stat and patch for a path."""
    try:
        cwd = path if os.path.isdir(path) else os.path.dirname(path) or "."
        result = subprocess.run(["git", "diff", "--stat", "--", path], capture_output=True, text=True, timeout=10, cwd=cwd)
        stat = result.stdout.strip()

        result2 = subprocess.run(["git", "diff", "--", path], capture_output=True, text=True, timeout=10, cwd=cwd)
        diff = result2.stdout.strip()

        if not stat and not diff:
            return "(git diff: no changes)"

        if len(diff) > 3000:
            diff = diff[:3000] + "\n... (truncated)"
        return f"--- git diff ---\n{stat}\n\n{diff}"
    except FileNotFoundError:
        return "(git is not installed)"
    except subprocess.TimeoutExpired:
        return "(git diff timed out)"


def _match_pattern(filename: str, pattern: str) -> bool:
    """Simple comma-separated glob matching."""
    import fnmatch

    for p in pattern.split(","):
        if fnmatch.fnmatch(filename, p.strip()):
            return True
    return False


TOOL_REGISTRY.register(
    name="search_code",
    func=search_code,
    description="Search text/regex in code files.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search text or regex"},
            "path": {"type": "string", "description": "Root path", "default": "."},
            "pattern": {"type": "string", "description": "File glob pattern", "default": "*.py"},
            "max_results": {"type": "integer", "description": "Maximum result count", "default": 30},
        },
        "required": ["query"],
    },
)

TOOL_REGISTRY.register(
    name="apply_patch",
    func=apply_patch,
    description="Replace one exact text block in a file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "old_string": {"type": "string", "description": "Exact original text"},
            "new_string": {"type": "string", "description": "Replacement text"},
        },
        "required": ["path", "old_string", "new_string"],
    },
)

TOOL_REGISTRY.register(
    name="show_diff",
    func=show_diff,
    description="Show git diff for a path.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to diff", "default": "."},
        },
        "required": [],
    },
)
