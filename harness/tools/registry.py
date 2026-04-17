"""도구 레지스트리 — 에이전트가 호출할 수 있는 도구를 등록/관리"""
from __future__ import annotations
import json
from typing import Callable, Any


class ToolRegistry:
    """도구를 이름으로 등록하고, JSON 스키마를 자동 생성하며, 이름으로 실행"""

    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        description: str,
        parameters: dict,
    ):
        self._tools[name] = {
            "name": name,
            "func": func,
            "description": description,
            "parameters": parameters,
        }

    def get(self, name: str) -> dict | None:
        return self._tools.get(name)

    def execute(self, name: str, arguments: dict) -> dict:
        """도구를 실행하고 결과를 반환. 항상 {ok, result/error} 형태."""
        tool = self._tools.get(name)
        if tool is None:
            return {"ok": False, "error": f"알 수 없는 도구: {name}"}
        try:
            result = tool["func"](**arguments)
            return {"ok": True, "result": result}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def schema_list(self) -> list[dict]:
        """모델에 주입할 도구 스키마 목록 반환"""
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            }
            for t in self._tools.values()
        ]

    def schema_text(self) -> str:
        """시스템 프롬프트에 포함할 도구 스키마 텍스트"""
        lines = []
        for t in self._tools.values():
            params = json.dumps(t["parameters"], ensure_ascii=False, indent=2)
            lines.append(
                f"### {t['name']}\n{t['description']}\n"
                f"Parameters:\n```json\n{params}\n```"
            )
        return "\n\n".join(lines)

    @property
    def names(self) -> list[str]:
        return list(self._tools.keys())


# 글로벌 레지스트리 인스턴스
TOOL_REGISTRY = ToolRegistry()
