"""에이전트 루프 엔진 — 탐색 → 수정 → 검증 반복 루프

진행방향.md 핵심 구조:
  사용자 입력 → 모델이 할 일 분해 → 파일 탐색 → 필요 파일만 주입 →
  패치 생성 → 테스트/린트 실행 → 결과 재주입 → 최종 요약 + diff

모델은 JSON으로만 응답하며, action 필드로 도구를 호출합니다.
"answer" action이면 사용자에게 답변을 전달하고 루프를 종료합니다.
"""
from __future__ import annotations
import json
import re
import time
import requests
from typing import Optional, Callable

from harness.context_manager import ContextManager
from harness.prompts.system_prompt import AGENT_SYSTEM_PROMPT
from harness.tools.registry import TOOL_REGISTRY

# 도구 모듈 임포트 (레지스트리에 자동 등록됨)
import harness.tools.file_tools
import harness.tools.code_tools
import harness.tools.command_tools


class AgentLoop:
    """LLM 기반 에이전트 루프. 도구 호출 → 결과 피드백 → 재판단을 반복."""

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
        self.on_step = on_step  # 각 단계 콜백 (UI 연동용)

        self.context = ContextManager(max_turns=10, max_chars=8000)
        self._build_system_prompt()

    def _build_system_prompt(self):
        """도구 스키마를 시스템 프롬프트에 주입"""
        tool_schemas = TOOL_REGISTRY.schema_text()
        self.system_prompt = AGENT_SYSTEM_PROMPT.replace("{tool_schemas}", tool_schemas)

    def run(self, user_input: str) -> str:
        """사용자 입력을 받아 에이전트 루프를 실행하고 최종 답변을 반환"""
        self.context.add_user(user_input)
        self._emit_step({"type": "user_input", "content": user_input})

        for i in range(self.max_iterations):
            # 1) LLM 호출
            self._emit_step({"type": "thinking", "iteration": i + 1})
            response = self._call_llm()

            if response is None:
                return "[오류] LLM 응답을 받지 못했습니다."

            # 2) JSON 파싱
            parsed = self._parse_response(response)
            if parsed is None:
                # JSON 파싱 실패 — 모델에게 재시도 요청
                self.context.add_assistant(response)
                self.context.add_tool_result(
                    "system",
                    "오류: JSON 형식으로 응답하세요. "
                    '{"thought": "...", "action": "도구명", "arguments": {...}}'
                )
                self._emit_step({"type": "parse_error", "raw": response[:200]})
                continue

            thought = parsed.get("thought", "")
            action = parsed.get("action", "")
            arguments = parsed.get("arguments", {})

            self.context.add_assistant(json.dumps(parsed, ensure_ascii=False))
            self._emit_step({
                "type": "action",
                "iteration": i + 1,
                "thought": thought,
                "action": action,
                "arguments": arguments,
            })

            # 3) answer → 루프 종료
            if action == "answer":
                answer_text = arguments.get("text", thought)
                return answer_text

            # 4) 도구 실행
            result = TOOL_REGISTRY.execute(action, arguments)

            if result["ok"]:
                result_text = str(result["result"])
            else:
                result_text = f"[도구 오류] {result['error']}"

            self.context.add_tool_result(action, result_text)
            self._emit_step({
                "type": "tool_result",
                "tool": action,
                "ok": result["ok"],
                "result": result_text[:500],
            })

        return "[경고] 최대 반복 횟수에 도달했습니다. 작업이 완료되지 않았을 수 있습니다."

    def _call_llm(self) -> Optional[str]:
        """LLM API를 호출하여 응답 텍스트를 반환"""
        messages = self.context.get_messages(self.system_prompt)

        payload = {
            "messages": [
                {"role": m["role"], "content": m["content"]}
                for m in messages
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        try:
            r = requests.post(
                f"{self.api_url}/chat",
                json=payload,
                timeout=300,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("response", "")
        except requests.exceptions.ConnectionError:
            return None
        except Exception as e:
            return None

    def _parse_response(self, text: str) -> Optional[dict]:
        """모델 응답에서 JSON 객체를 추출"""
        text = text.strip()

        # 1) 전체가 JSON인 경우
        try:
            obj = json.loads(text)
            if self._is_valid_action(obj):
                return obj
        except json.JSONDecodeError:
            pass

        # 2) ```json ... ``` 블록 추출
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(1).strip())
                if self._is_valid_action(obj):
                    return obj
            except json.JSONDecodeError:
                pass

        # 3) { ... } 블록 추출 (greedy)
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
        """파싱된 JSON이 유효한 에이전트 액션인지 확인"""
        return (
            isinstance(obj, dict)
            and "action" in obj
            and isinstance(obj.get("arguments", {}), dict)
        )

    def _emit_step(self, step: dict):
        """단계 콜백 호출 (UI 연동용)"""
        if self.on_step:
            self.on_step(step)

    def reset(self):
        """대화 및 상태 초기화"""
        self.context.reset()
