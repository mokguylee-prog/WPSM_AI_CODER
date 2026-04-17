"""Tool registry used by the agent runtime."""
from __future__ import annotations

import json
from typing import Callable, Any


class ToolRegistry:
    """Register tools and execute them by name."""

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
        """Execute a tool and return a normalized result."""
        tool = self._tools.get(name)
        if tool is None:
            return {"ok": False, "error": f"Unknown tool: {name}", "error_type": "unknown_tool"}
        try:
            result = tool["func"](**arguments)
            return {"ok": True, "result": result}
        except PermissionError as e:
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "error_type": "permission",
                "error_class": type(e).__name__,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "error_type": "exception",
                "error_class": type(e).__name__,
            }

    def schema_list(self) -> list[dict]:
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            }
            for t in self._tools.values()
        ]

    def schema_text(self) -> str:
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


TOOL_REGISTRY = ToolRegistry()
