"""Agent loop engine.

The model must respond in JSON and choose one action at a time.
When action is "answer", the loop ends and returns text to the user.
"""
from __future__ import annotations

import json
import re
import time
import os
import requests
from typing import Optional, Callable

# P4-2: 留덉?留??좏겙 ?섏떊 ?????쒓컙(珥? ?숈븞 ?묐떟???놁쑝硫??ㅽ듃由쇱쓣 ?딅뒗??
# ?⑥씪 300s ??꾩븘?껋? ?먭린?섏뿀怨? connect ??꾩븘?껋? 蹂꾨룄濡?10s ?좎??쒕떎.
IDLE_TIMEOUT_S: float = 60.0

from Sm_AIAgent.context_manager import ContextManager
from Sm_AIAgent.prompts.system_prompt import AGENT_SYSTEM_PROMPT
from Sm_AIAgent.tools.registry import TOOL_REGISTRY

# Import tool modules so they self-register in TOOL_REGISTRY.
import Sm_AIAgent.tools.file_tools
import Sm_AIAgent.tools.code_tools
import Sm_AIAgent.tools.command_tools

# P3-3: ?곗냽 ?뚯떛 ?ㅽ뙣 ?덉슜 ?잛닔 ?곹븳. ??媛믪쓣 珥덇낵?섎㈃ 猷⑦봽瑜?媛뺤젣 醫낅즺?쒕떎.
MAX_PARSE_RETRIES = 2

# P6-2: prompt ?좏겙 異붿젙 ?꾧퀎 ??len(prompt)//4 蹂댁닔移?湲곗?.
# ??媛믪쓣 珥덇낵?섎㈃ step{"kind":"warn", "msg":"prompt too large"} 瑜?諛쒗뻾?쒕떎.
PROMPT_TOKEN_WARN_THRESHOLD = 3000


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
        force_json: bool = False,
    ):
        self.api_url = api_url
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.working_dir = working_dir
        self.on_step = on_step
        # P3-1: True ?대㈃ /chat ?몄텧 ??force_json=True 瑜??쒕쾭???꾨떖
        self.force_json = force_json
        # ?먯씠?꾪듃???덉젙?깆쓣 ?곗꽑?댁꽌 釉붾줈??JSON ?묐떟 寃쎈줈瑜?湲곕낯 ?ъ슜?쒕떎.
        self.force_json = True
        self._retry_hint_added = False

        self.context = ContextManager(max_turns=10, max_chars=8000)
        self._used_file_edit_tool = False
        self._needs_file_edit = False
        self._cancel_requested = False
        # P3-3: ?곗냽 ?뚯떛 ?ㅽ뙣 ?잛닔 異붿쟻
        self._parse_fail_count = 0
        self._build_system_prompt()

    def _build_system_prompt(self):
        """Inject tool schemas into system prompt."""
        tool_schemas = TOOL_REGISTRY.schema_text()
        self.system_prompt = AGENT_SYSTEM_PROMPT.replace("{tool_schemas}", tool_schemas)

    def run(self, user_input: str) -> str:
        """Run the agent loop for one user request."""
        self._cancel_requested = False
        self._needs_file_edit = self._looks_like_file_task(user_input)
        self._used_file_edit_tool = False
        # P3-3: ???붿껌留덈떎 ?곗냽 ?뚯떛 ?ㅽ뙣 移댁슫??珥덇린??        self._parse_fail_count = 0
        self.context.add_user(user_input)
        self._emit_step({"type": "user_input", "content": user_input})

        if self._looks_like_winforms_scaffold_request(user_input):
            scaffold_result = self._create_winforms_scaffold(user_input)
            self._emit_step({"type": "tool_result", "tool": "winforms_scaffold", "ok": True, "result": scaffold_result[:500]})
            return scaffold_result

        for i in range(self.max_iterations):
            if self._cancel_requested:
                self._emit_step({"type": "cancelled", "iteration": i + 1})
                return "[痍⑥냼?? ?ъ슜???붿껌?쇰줈 ?먯씠?꾪듃 ?ㅽ뻾??以묐떒?섏뿀?듬땲??"
            self._emit_step({"type": "thinking", "iteration": i + 1})
            response = self._call_llm()

            if response is None:
                return "[?ㅻ쪟] LLM ?묐떟??諛쏆? 紐삵뻽?듬땲??"

            parsed = self._parse_response(response)
            if parsed is None:
                # P3-3: ?곗냽 ?ㅽ뙣 移댁슫??利앷?
                self._parse_fail_count += 1
                self._emit_step({
                    "type": "parse_error",
                    "raw": response[:200],
                    "fail_count": self._parse_fail_count,
                })

                if self._parse_fail_count > MAX_PARSE_RETRIES:
                    # ?곹븳 珥덇낵 ??猷⑦봽瑜?媛뺤젣 醫낅즺?섍퀬 ?ъ슜?먯뿉寃??덈궡
                    abort_msg = (
                        "?꾧뎄 ?몄텧 ?뺤떇???몄떇?섏? 紐삵빐 醫낅즺?⑸땲?? "
                        f"(?곗냽 {self._parse_fail_count}???뚯떛 ?ㅽ뙣)"
                    )
                    self._emit_step({"type": "parse_abort", "message": abort_msg})
                    return abort_msg

                self.context.add_assistant(response)
                self.context.add_tool_result(
                    "system",
                    "Error: respond with exactly one JSON object using the required schema.",
                )
                if not self._retry_hint_added:
                    self._retry_hint_added = True
                    retry_prompt = (
                        "Return only one valid JSON object. "
                        "Do not include explanations, markdown fences, or extra text."
                    )
                    self.context.add_tool_result("system", retry_prompt)
                    self._emit_step({"type": "parse_retry", "message": retry_prompt})
                continue

            # ?뚯떛 ?깃났 ??移댁슫??珥덇린??            self._parse_fail_count = 0

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
                        "This request requires actual file creation or modification. Do not end with answer yet. "
                        "Use list_files/search_code/read_file first if needed, then write_file or apply_patch "
                        "so the filesystem is actually updated."
                    )
                    self.context.add_tool_result("system", reminder)
                    self._emit_step({"type": "tool_result", "tool": "system", "ok": False, "result": reminder})
                    continue

                if self._used_file_edit_tool:
                    diff_result = TOOL_REGISTRY.execute("show_diff", {"path": self.working_dir})
                    diff_text = str(diff_result["result"]) if diff_result["ok"] else f"[?袁㏓럡 ??살첒] {diff_result['error']}"
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
            result_text = str(result["result"]) if result["ok"] else f"[?꾧뎄 ?ㅻ쪟] {result['error']}"

            if action in {"write_file", "apply_patch"} and result["ok"]:
                self._used_file_edit_tool = True
            if action == "run_command" and not result["ok"] and result.get("error_type") == "permission":
                approval_msg = "沅뚰븳???꾩슂??紐낅졊??李⑤떒?섏뿀?듬땲?? ?ъ슜???뱀씤 ???ㅼ떆 ?쒕룄?댁빞 ?⑸땲??"
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

        return "[寃쎄퀬] 理쒕? 諛섎났 ?잛닔???꾨떖?덉뒿?덈떎. ?묒뾽???꾨즺?섏? ?딆븯?????덉뒿?덈떎."

    def cancel(self):
        self._cancel_requested = True

    def _estimate_prompt_tokens(self, messages: list[dict]) -> int:
        """P6-2: 硫붿떆吏 ?꾩껜 ?띿뒪??湲몄씠瑜?湲곗??쇰줈 ?좏겙 ?섎? 蹂댁닔?곸쑝濡?異붿젙?쒕떎.
        ?ㅼ젣 ?좏겕?섏씠? ?놁씠???숈옉?섎룄濡?len(text)//4 怨듭떇???ъ슜?쒕떎.
        """
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars // 4

    def _call_llm(self) -> Optional[str]:
        """Call local LLM via /chat/stream (NDJSON) and return accumulated response.

        P4-1: ?좏겙 ?섏떊留덈떎 step{"kind":"token", "n":int} ?대깽?몃? 諛쒗뻾?쒕떎.
              /agent/stream 履?on_step 肄쒕갚???듯빐 GUI媛 "?앹꽦以?N ?좏겙" ?쒖떆??              ?ъ슜?????덈떎.

        P4-2: idle-timeout ??留덉?留??좏겙/heartbeat ?댄썑 IDLE_TIMEOUT_S 珥??숈븞
              ???곗씠?곌? ?놁쑝硫?ConnectionError 濡?痍④툒??None ??諛섑솚?쒕떎.
              300s ?⑥씪 ??꾩븘?껋? ?먭린?쒕떎.
              遺遺?寃곌낵(?대? ?볦씤 ?좏겙)??踰꾨━吏 ?딄퀬 ?몄텧?먯뿉寃?諛섑솚?쒕떎.

        P6-2: ?몄텧 ???꾨＼?꾪듃 ?좏겙??異붿젙?섏뿬 PROMPT_TOKEN_WARN_THRESHOLD 珥덇낵 ??              step{"kind":"warn", "msg":"prompt too large", ...} 瑜?諛쒗뻾?쒕떎.
        """
        messages = self.context.get_messages(self.system_prompt)

        # P6-2: prompt ?좏겙 異붿젙 寃쎄퀬
        estimated_tokens = self._estimate_prompt_tokens(messages)
        if estimated_tokens > PROMPT_TOKEN_WARN_THRESHOLD:
            self._emit_step({
                "kind": "warn",
                "type": "warn",
                "msg": "prompt too large",
                "estimated_tokens": estimated_tokens,
                "threshold": PROMPT_TOKEN_WARN_THRESHOLD,
            })
        # force_json ?대㈃ /chat?force_json=true 瑜??⑥빞 ?섎뒗??/chat/stream ?먮뒗
        # force_json ?뚮씪誘명꽣媛 ?놁쑝誘濡?洹?寃쎌슦留?鍮꾩뒪?몃━諛?/chat ???좎??쒕떎.
        if self.force_json:
            return self._call_llm_blocking()

        payload = {
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            # P6-3: ??쒕낫??kind 而щ읆?????몄텧??agent-step ?꾩쓣 ?뚮┛??
            "kind": "agent-step",
        }

        chunks: list[str] = []
        token_count = 0
        last_activity = time.monotonic()  # P4-2: idle-timeout 湲곗???
        try:
            # connect=10s, read=None(?ㅽ듃由쇱씠誘濡?iter_lines 媛 吏곸젒 愿由?
            with requests.post(
                f"{self.api_url}/chat/stream",
                json=payload,
                stream=True,
                timeout=(10, None),
            ) as r:
                r.raise_for_status()
                for raw in r.iter_lines(decode_unicode=True):
                    if self._cancel_requested:
                        break

                    # P4-2: idle-timeout 寃????iter_lines ????以꾩쓣 諛쏆븘?쇰쭔 猷⑦봽
                    # 蹂몄껜???ㅼ뼱?ㅻ?濡?TCP ?덈꺼 釉붾줈???곹깭?먯꽌????寃?ъ뿉 ?꾨떖?섏?
                    # 紐삵븳?? ?ㅼ쭏?곸씤 idle-timeout ? ?쒕쾭 gen() ?먯꽌 heartbeat ?놁씠
                    # IDLE_TIMEOUT_S 珥?寃쎄낵 ??error ?대깽?몃? 諛쒗뻾?⑥쑝濡쒖뜥 ?대（?댁쭊??
                    # ??寃?щ뒗 heartbeat 瑜?諛쏆븯吏留?token ???녿뒗 洹밸떒??寃쎌슦瑜??꾪븳
                    # 2李?諛⑹뼱?좎씠??
                    now = time.monotonic()
                    if now - last_activity > IDLE_TIMEOUT_S:
                        self._emit_step({
                            "type": "idle_timeout",
                            "idle_s": round(now - last_activity, 1),
                            "partial_tokens": token_count,
                        })
                        break

                    if not raw:
                        continue

                    try:
                        evt = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    last_activity = time.monotonic()  # ?좏슚 ?곗씠???섏떊 ??由ъ뀑

                    t = evt.get("type")
                    if t == "token":
                        token = evt.get("text", "")
                        if token:
                            chunks.append(token)
                            token_count += 1
                            # P4-1: ?좏겙留덈떎 step ?대깽??諛쒗뻾
                            self._emit_step({
                                "kind": "token",
                                "type": "token",
                                "n": token_count,
                            })
                    elif t == "final":
                        # ?쒕쾭媛 final ??蹂대궡硫??뺤긽 ?꾨즺
                        final_response = evt.get("response")
                        if final_response:
                            return final_response
                        break
                    elif t == "error":
                        self._emit_step({"type": "llm_error", "error": evt.get("error", "")})
                        return "".join(chunks) if chunks else None
                    # heartbeat ??last_activity ?대? 媛깆떊??
        except requests.exceptions.ConnectionError:
            return None
        except requests.exceptions.Timeout:
            return None
        except Exception:
            return None

        return "".join(chunks) if chunks else None

    def _call_llm_blocking(self) -> Optional[str]:
        """force_json 紐⑤뱶 ?꾩슜 ??鍮꾩뒪?몃━諛?/chat ?몄텧 (GBNF 洹몃옒癒??꾩슂).

        P4-2: ??寃쎈줈??IDLE_TIMEOUT_S 媛 ?곸슜?섏? ?딅뒗??
              force_json=True ?ъ슜?먮뒗 湲??湲곕? 媛먯닔?댁빞 ?쒕떎.
        """
        messages = self.context.get_messages(self.system_prompt)
        payload = {
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "force_json": True,
        }
        try:
            r = requests.post(f"{self.api_url}/chat", json=payload, timeout=(10, 300))
            r.raise_for_status()
            data = r.json()
            return data.get("response", "")
        except requests.exceptions.ConnectionError:
            return None
        except Exception:
            return None

    def _parse_response(self, text: str) -> Optional[dict]:
        """Extract JSON action object from model output.

        ?뚯떛 ?쒖꽌:
        1. ?쒖닔 JSON ?뚯떛 (媛??鍮좊쫫)
        2. ```json ... ``` 肄붾뱶 釉붾줉 異붿텧 ???뚯떛
        3. ?띿뒪????泥?踰덉㎏ {...} 釉붾줉 ?뚯떛
        4. P3-2: Qwen native <tool_call>...</tool_call> XML ?대갚
           - ?대? JSON ??異붿텧??tool_name / arguments ?ㅻ?
             ?먯씠?꾪듃媛 ?ъ슜?섎뒗 action / arguments ?ㅻ줈 蹂??        """
        text = text.strip()

        # 1. ?쒖닔 JSON
        try:
            obj = json.loads(text)
            if self._is_valid_action(obj):
                return obj
        except json.JSONDecodeError:
            pass

        # 2. 留덊겕?ㅼ슫 肄붾뱶 釉붾줉
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(1).strip())
                if self._is_valid_action(obj):
                    return obj
            except json.JSONDecodeError:
                pass

        # 3. 泥?踰덉㎏ 以묎큵??釉붾줉
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(0))
                if self._is_valid_action(obj):
                    return obj
            except json.JSONDecodeError:
                pass

        # 4. P3-2: Qwen native <tool_call>...</tool_call> XML ?대갚
        #    Qwen2.5 ??JSON 洹몃옒癒??놁씠 ?ㅽ뻾 ???꾨옒 ?뺤떇??異쒕젰?섍린???쒕떎:
        #      <tool_call>{"name": "read_file", "arguments": {...}}</tool_call>
        #    ?먮뒗 arguments ???parameters ?ㅻ? ?ъ슜?섎뒗 蹂?뺣룄 泥섎━?쒕떎.
        xml_match = re.search(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL)
        if xml_match:
            try:
                inner = xml_match.group(1).strip()
                tc = json.loads(inner)
                if isinstance(tc, dict):
                    # tool_name ? "name" ?먮뒗 "tool_name" ?ㅻ줈 ?????덈떎
                    tool_name = tc.get("name") or tc.get("tool_name", "")
                    # arguments ??"arguments" ?먮뒗 "parameters" ?ㅻ줈 ?????덈떎
                    arguments = tc.get("arguments") or tc.get("parameters") or {}
                    if isinstance(arguments, dict) and tool_name:
                        normalized = {
                            "thought": tc.get("thought", ""),
                            "action": tool_name,
                            "arguments": arguments,
                        }
                        if self._is_valid_action(normalized):
                            return normalized
            except (json.JSONDecodeError, AttributeError):
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
        self._parse_fail_count = 0
        self._retry_hint_added = False

    def _looks_like_winforms_scaffold_request(self, text: str) -> bool:
        lowered = text.lower()
        hints = [
            "winform", "winforms", "windows form", "c# winform", "c# winforms",
            "form1", "designer", "csproj", "윈폼", "windows forms",
        ]
        keywords = ["example", "예제", "sample", "샘플", "만들어", "create", "scaffold", "project", "프로젝트"]
        return any(h in lowered for h in hints) and any(k in lowered for k in keywords)

    def _create_winforms_scaffold(self, user_input: str) -> str:
        base_dir = self.working_dir if os.path.isdir(self.working_dir) else "."
        project_dir = os.path.join(base_dir, "WinFormsExample")
        os.makedirs(project_dir, exist_ok=True)

        files = {
            os.path.join(project_dir, "Program.cs"): """using System;\nusing System.Windows.Forms;\n\nnamespace WinFormsExample\n{\n    internal static class Program\n    {\n        [STAThread]\n        private static void Main()\n        {\n            ApplicationConfiguration.Initialize();\n            Application.Run(new Form1());\n        }\n    }\n}\n""",
            os.path.join(project_dir, "Form1.cs"): """using System.Windows.Forms;\n\nnamespace WinFormsExample\n{\n    public partial class Form1 : Form\n    {\n        public Form1()\n        {\n            InitializeComponent();\n        }\n    }\n}\n""",
            os.path.join(project_dir, "Form1.Designer.cs"): """namespace WinFormsExample\n{\n    partial class Form1\n    {\n        private System.ComponentModel.IContainer components = null;\n\n        protected override void Dispose(bool disposing)\n        {\n            if (disposing && (components != null))\n            {\n                components.Dispose();\n            }\n            base.Dispose(disposing);\n        }\n\n        private void InitializeComponent()\n        {\n            this.SuspendLayout();\n            this.ClientSize = new System.Drawing.Size(800, 450);\n            this.Text = \"WinForms Example\";\n            this.ResumeLayout(false);\n        }\n    }\n}\n""",
            os.path.join(project_dir, "Form1.resx"): """<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<root>\n  <resheader name=\"resmimetype\"><value>text/microsoft-resx</value></resheader>\n  <resheader name=\"version\"><value>2.0</value></resheader>\n  <resheader name=\"reader\"><value>System.Resources.ResXResourceReader, System.Windows.Forms, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089</value></resheader>\n  <resheader name=\"writer\"><value>System.Resources.ResXResourceWriter, System.Windows.Forms, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089</value></resheader>\n</root>\n""",
            os.path.join(project_dir, "WinFormsExample.csproj"): """<Project Sdk=\"Microsoft.NET.Sdk.WindowsDesktop\">\n  <PropertyGroup>\n    <OutputType>WinExe</OutputType>\n    <TargetFramework>net8.0-windows</TargetFramework>\n    <UseWindowsForms>true</UseWindowsForms>\n    <Nullable>enable</Nullable>\n    <ImplicitUsings>enable</ImplicitUsings>\n  </PropertyGroup>\n</Project>\n""",
        }
        saved = []
        from Sm_AIAgent.tools.registry import TOOL_REGISTRY
        for path, content in files.items():
            result = TOOL_REGISTRY.execute("write_file", {"path": path, "content": content})
            if result["ok"]:
                saved.append(path)
        return "WinForms scaffold created:\n" + "\n".join(f"- {p}" for p in saved)

    def detect_scaffold_type(self, text: str) -> str:
        lowered = text.lower()
        if any(k in lowered for k in ("winform", "winforms", "윈폼")):
            return "winforms"
        if any(k in lowered for k in ("python", "flask", "django", "fastapi")):
            return "python"
        if any(k in lowered for k in ("react", "node", "npm", "javascript", "typescript")):
            return "node"
        if any(k in lowered for k in ("java", "spring")):
            return "java"
        if any(k in lowered for k in ("c++", "cpp", "cmake")):
            return "cpp"
        return "generic"

    def create_scaffold(self, text: str) -> str:
        scaffold = self.detect_scaffold_type(text)
        base_dir = self.working_dir if os.path.isdir(self.working_dir) else "."
        root_name = "GeneratedProject"
        if scaffold == "python":
            root_name = "PythonExample"
        elif scaffold == "node":
            root_name = "NodeExample"
        elif scaffold == "java":
            root_name = "JavaExample"
        elif scaffold == "cpp":
            root_name = "CppExample"
        elif scaffold == "winforms":
            return self._create_winforms_scaffold(text)

        project_dir = os.path.join(base_dir, root_name)
        os.makedirs(project_dir, exist_ok=True)
        from Sm_AIAgent.tools.registry import TOOL_REGISTRY
        created = []

        def write(rel_path: str, content: str):
            abs_path = os.path.join(project_dir, rel_path)
            result = TOOL_REGISTRY.execute("write_file", {"path": abs_path, "content": content})
            if result["ok"]:
                created.append(abs_path)

        if scaffold == "python":
            write("main.py", 'def main():\n    print("Hello from Python example")\n\nif __name__ == "__main__":\n    main()\n')
            write("requirements.txt", "")
            write("README.md", "# Python Example\n")
        elif scaffold == "node":
            write("package.json", '{\n  "name": "node-example",\n  "private": true,\n  "scripts": {\n    "start": "node src/index.js"\n  }\n}\n')
            write(os.path.join("src", "index.js"), 'console.log("Hello from Node example");\n')
        elif scaffold == "java":
            write(os.path.join("src", "main", "java", "Main.java"), 'public class Main { public static void main(String[] args) { System.out.println("Hello from Java example"); } }\n')
            write("pom.xml", "<project></project>\n")
        elif scaffold == "cpp":
            write("main.cpp", '#include <iostream>\nint main(){ std::cout << "Hello from C++ example\\n"; }\n')
            write("CMakeLists.txt", "cmake_minimum_required(VERSION 3.10)\nproject(CppExample)\nadd_executable(CppExample main.cpp)\n")
        else:
            write("README.md", "# Generated Project\n")

        return f"{scaffold} scaffold created:\n" + "\n".join(f"- {p}" for p in created)

    def _looks_like_file_task(self, text: str) -> bool:
        lowered = text.lower()
        keywords = [
            "create", "new file", "new folder", "write", "edit", "modify",
            "fix", "patch", "update", "remove", "delete", "scaffold", "sample",
            "example", "template", "project", "solution", "winform", "windows form",
            "c#", ".cs", ".csproj", "예제", "샘플", "프로젝트", "윈폼",
        ]
        return any(keyword in lowered for keyword in keywords)
