"""Agent loop engine.

The model must respond in JSON and choose one action at a time.
When action is "answer", the loop ends and returns text to the user.
"""
from __future__ import annotations

import json
import re
import requests
from typing import Optional, Callable

from Sm_AIAgent.context_manager import ContextManager
from Sm_AIAgent.prompts.system_prompt import AGENT_SYSTEM_PROMPT
from Sm_AIAgent.tools.registry import TOOL_REGISTRY

# Import tool modules so they self-register in TOOL_REGISTRY.
import Sm_AIAgent.tools.file_tools
import Sm_AIAgent.tools.code_tools
import Sm_AIAgent.tools.command_tools


class AgentLoop:
    """LLM-based agent loop that executes one tool action per turn."""

    def __init__(
        self,
        api_url: str = "http://localhost:8888",
        max_iterations: int = 15,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        working_dir: str = ".",
        on_step: Optional[Callable[[dict], None]] = None,
    ):
        self.api_url = api_url
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.working_dir = working_dir
        self.on_step = on_step

        self.context = ContextManager(max_turns=10, max_chars=8000)
        self._used_file_edit_tool = False
        self._needs_file_edit = False
        self._build_system_prompt()

    def _build_system_prompt(self):
        """Inject tool schemas into system prompt."""
        tool_schemas = TOOL_REGISTRY.schema_text()
        self.system_prompt = AGENT_SYSTEM_PROMPT.replace("{tool_schemas}", tool_schemas)

    def run(self, user_input: str) -> str:
        """Run the agent loop for one user request."""
        self._needs_file_edit = self._looks_like_edit_request(user_input)
        self._used_file_edit_tool = False
        self.context.add_user(user_input)
        self._emit_step({"type": "user_input", "content": user_input})

        for i in range(self.max_iterations):
            self._emit_step({"type": "thinking", "iteration": i + 1})
            response = self._call_llm()

            if response is None:
                return "[오류] LLM 응답을 받지 못했습니다."

            parsed = self._parse_response(response)
            if parsed is None:
                self.context.add_assistant(response)
                self.context.add_tool_result(
                    "system",
                    "오류: JSON 형식으로 응답하세요. "
                    '{"thought": "...", "action": "도구명", "arguments": {...}}',
                )
                self._emit_step({"type": "parse_error", "raw": response[:200]})
                continue

            thought = parsed.get("thought", "")
            action = parsed.get("action", "")
            arguments = parsed.get("arguments", {})

            self.context.add_assistant(json.dumps(parsed, ensure_ascii=False))
            self._emit_step(
                {
                    "type": "action",
                    "iteration": i + 1,
                    "thought": thought,
                    "action": action,
                    "arguments": arguments,
                }
            )

            if action == "answer":
                if self._needs_file_edit and not self._used_file_edit_tool:
                    reminder = (
                        "This request is a file edit/create task. Do not end with answer yet. "
                        "Use read_file/list_files/search_code first, then write_file or apply_patch "
                        "so the filesystem is actually updated."
                    )
                    self.context.add_tool_result("system", reminder)
                    self._emit_step({"type": "tool_result", "tool": "system", "ok": False, "result": reminder})
                    continue

                if self._used_file_edit_tool:
                    diff_result = TOOL_REGISTRY.execute("show_diff", {"path": self.working_dir})
                    diff_text = str(diff_result["result"]) if diff_result["ok"] else f"[?꾧뎄 ?ㅻ쪟] {diff_result['error']}"
                    self.context.add_tool_result("show_diff", diff_text)
                    self._emit_step(
                        {
                            "type": "tool_result",
                            "tool": "show_diff",
                            "ok": diff_result["ok"],
                            "result": diff_text[:500],
                        }
                    )
                    continue

                return arguments.get("text", thought)

            result = TOOL_REGISTRY.execute(action, arguments)
            result_text = str(result["result"]) if result["ok"] else f"[도구 오류] {result['error']}"

            if action in {"write_file", "apply_patch"} and result["ok"]:
                self._used_file_edit_tool = True
            if action == "run_command" and not result["ok"] and result.get("error_type") == "permission":
                approval_msg = "권한이 필요한 명령이 차단되었습니다. 사용자 승인 후 다시 시도해야 합니다."
                if "Allowed prefixes:" in result["error"]:
                    approval_msg += "\n" + result["error"]
                self.context.add_tool_result(action, approval_msg)
                self._emit_step(
                    {
                        "type": "approval_required",
                        "tool": action,
                        "command": arguments.get("command", ""),
                        "timeout": arguments.get("timeout", 30),
                        "message": approval_msg,
                    }
                )
                return approval_msg
            self.context.add_tool_result(action, result_text)
            self._emit_step(
                {
                    "type": "tool_result",
                    "tool": action,
                    "ok": result["ok"],
                    "result": result_text[:500],
                }
            )

        return "[경고] 최대 반복 횟수에 도달했습니다. 작업이 완료되지 않았을 수 있습니다."

    def _call_llm(self) -> Optional[str]:
        """Call local LLM API and return response text."""
        messages = self.context.get_messages(self.system_prompt)
        payload = {
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        try:
            r = requests.post(f"{self.api_url}/chat", json=payload, timeout=300)
            r.raise_for_status()
            data = r.json()
            return data.get("response", "")
        except requests.exceptions.ConnectionError:
            return None
        except Exception:
            return None

    def _parse_response(self, text: str) -> Optional[dict]:
        """Extract JSON object from model output."""
        text = text.strip()

        try:
            obj = json.loads(text)
            if self._is_valid_action(obj):
                return obj
        except json.JSONDecodeError:
            pass

        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(1).strip())
                if self._is_valid_action(obj):
                    return obj
            except json.JSONDecodeError:
                pass

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(0))
                if self._is_valid_action(obj):
                    return obj
            except json.JSONDecodeError:
                pass

        return None

    def _is_valid_action(self, obj: dict) -> bool:
        """Return True when object has valid action payload."""
        return isinstance(obj, dict) and "action" in obj and isinstance(obj.get("arguments", {}), dict)

    def _emit_step(self, step: dict):
        """Emit step callback for UI streaming."""
        if self.on_step:
            self.on_step(step)

    def reset(self):
        """Reset conversation context."""
        self.context.reset()
        self._used_file_edit_tool = False
        self._needs_file_edit = False

    def _looks_like_edit_request(self, text: str) -> bool:
        lowered = text.lower()
        keywords = [
            "create", "new file", "new folder", "write", "edit", "modify",
            "fix", "patch", "update", "remove", "delete", "구현", "수정",
            "생성", "추가", "변경", "버그", "고쳐", "파일", "폴더",
        ]
        return any(keyword in lowered for keyword in keywords)
