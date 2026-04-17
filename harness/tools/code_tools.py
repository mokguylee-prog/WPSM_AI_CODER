"""코드 관련 도구 — search_code, apply_patch, show_diff"""
from __future__ import annotations
import os
import re
import subprocess
import difflib
from harness.tools.registry import TOOL_REGISTRY


def search_code(query: str, path: str = ".", pattern: str = "*.py",
                max_results: int = 30) -> str:
    """코드베이스에서 문자열/정규식을 검색합니다."""
    if not os.path.isdir(path):
        raise NotADirectoryError(f"디렉토리 없음: {path}")

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
        return f"('{query}' 검색 결과 없음)"
    header = f"검색: '{query}' — {len(results)}건"
    return header + "\n" + "\n".join(results)


def apply_patch(path: str, old_string: str, new_string: str) -> str:
    """파일에서 old_string을 찾아 new_string으로 교체합니다 (패치 방식)."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"파일 없음: {path}")

    with open(path, "r", encoding="utf-8") as f:
        original = f.read()

    count = original.count(old_string)
    if count == 0:
        raise ValueError(
            f"old_string을 파일에서 찾을 수 없습니다.\n"
            f"파일: {path}\n"
            f"찾으려는 문자열 (처음 100자): {old_string[:100]!r}"
        )
    if count > 1:
        raise ValueError(
            f"old_string이 {count}번 발견됩니다. 더 구체적인 문자열을 제공하세요."
        )

    modified = original.replace(old_string, new_string, 1)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(modified)

    # diff 생성
    diff = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        fromfile=f"a/{os.path.basename(path)}",
        tofile=f"b/{os.path.basename(path)}",
        lineterm="",
    ))
    diff_text = "\n".join(diff[:50]) if diff else "(변경 없음)"
    return f"패치 적용 완료: {path}\n{diff_text}"


def show_diff(path: str = ".") -> str:
    """git diff를 실행하여 변경 사항을 보여줍니다."""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "--", path],
            capture_output=True, text=True, timeout=10,
            cwd=path if os.path.isdir(path) else os.path.dirname(path) or ".",
        )
        stat = result.stdout.strip()

        result2 = subprocess.run(
            ["git", "diff", "--", path],
            capture_output=True, text=True, timeout=10,
            cwd=path if os.path.isdir(path) else os.path.dirname(path) or ".",
        )
        diff = result2.stdout.strip()

        if not stat and not diff:
            return "(git diff: 변경 사항 없음)"

        # 너무 길면 잘라냄
        if len(diff) > 3000:
            diff = diff[:3000] + "\n... (생략됨)"
        return f"--- git diff ---\n{stat}\n\n{diff}"
    except FileNotFoundError:
        return "(git이 설치되지 않았습니다)"
    except subprocess.TimeoutExpired:
        return "(git diff 시간 초과)"


def _match_pattern(filename: str, pattern: str) -> bool:
    """간단한 확장자 패턴 매칭"""
    import fnmatch
    for p in pattern.split(","):
        if fnmatch.fnmatch(filename, p.strip()):
            return True
    return False


# ── 레지스트리 등록 ──
TOOL_REGISTRY.register(
    name="search_code",
    func=search_code,
    description="코드베이스에서 문자열이나 정규식을 검색합니다.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "검색할 문자열 또는 정규식"},
            "path": {"type": "string", "description": "검색 시작 디렉토리", "default": "."},
            "pattern": {"type": "string", "description": "파일 패턴 (예: *.py,*.js)", "default": "*.py"},
            "max_results": {"type": "integer", "description": "최대 결과 수", "default": 30},
        },
        "required": ["query"],
    },
)

TOOL_REGISTRY.register(
    name="apply_patch",
    func=apply_patch,
    description="파일에서 old_string을 찾아 new_string으로 교체합니다. 정확히 1번만 매칭되어야 합니다.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "수정할 파일 경로"},
            "old_string": {"type": "string", "description": "교체할 기존 문자열 (정확히 일치해야 함)"},
            "new_string": {"type": "string", "description": "새로운 문자열"},
        },
        "required": ["path", "old_string", "new_string"],
    },
)

TOOL_REGISTRY.register(
    name="show_diff",
    func=show_diff,
    description="git diff로 현재 변경 사항을 확인합니다.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "diff를 확인할 경로", "default": "."},
        },
        "required": [],
    },
)
