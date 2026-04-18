"""컨텍스트 관리자 — 작은 모델을 위한 대화 압축 및 작업 상태 관리

진행방향.md 핵심:
- 작은 모델은 긴 대화를 넣으면 흔들린다
- 매 턴마다 전체 로그 대신 5가지 요약만 유지
- 현재 목표 / 관련 파일 / 최근 변경 / 테스트 결과 / 다음 행동
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field


@dataclass
class WorkState:
    """에이전트의 현재 작업 상태 (메모리 역할)"""
    goal: str = ""
    files: list[str] = field(default_factory=list)
    recent_changes: str = ""
    test_results: str = ""
    next_action: str = ""

    def to_text(self) -> str:
        if not self.goal:
            return ""
        return (
            f"## 현재 작업 상태\n"
            f"- 목표: {self.goal}\n"
            f"- 관련 파일: {', '.join(self.files) if self.files else '없음'}\n"
            f"- 최근 변경: {self.recent_changes or '없음'}\n"
            f"- 테스트 결과: {self.test_results or '없음'}\n"
            f"- 다음 행동: {self.next_action or '미정'}\n"
        )

    def update_from_dict(self, data: dict):
        if "goal" in data:
            self.goal = data["goal"]
        if "files" in data:
            self.files = data["files"]
        if "recent_changes" in data:
            self.recent_changes = data["recent_changes"]
        if "test_results" in data:
            self.test_results = data["test_results"]
        if "next_action" in data:
            self.next_action = data["next_action"]


class ContextManager:
    """대화 히스토리를 관리하고, 컨텍스트 길이를 제한하며, 작업 상태를 유지"""

    def __init__(self, max_turns: int = 6, max_chars: int = 4000):  # P2-3: 8→6, 6000→4000
        self.messages: list[dict] = []
        self.work_state = WorkState()
        self.max_turns = max_turns
        self.max_chars = max_chars
        self.turn_count = 0

    def add_user(self, content: str):
        self.messages.append({"role": "user", "content": content})
        self.turn_count += 1
        self._trim()

    def add_assistant(self, content: str):
        self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_tool_result(self, tool_name: str, result: str):
        """도구 실행 결과를 user 메시지로 추가 (모델이 tool role을 지원하지 않을 수 있으므로)"""
        # 결과가 너무 길면 잘라냄 (P2-3: 2000→800)
        if len(result) > 800:
            result = result[:800] + "\n... (결과 생략됨)"
        self.messages.append({
            "role": "user",
            "content": f"[도구 결과: {tool_name}]\n{result}",
        })
        self._trim()

    def get_messages(self, system_prompt: str) -> list[dict]:
        """시스템 프롬프트 + 작업 상태 + 최근 대화를 합쳐 반환"""
        msgs = [{"role": "system", "content": system_prompt}]

        # 작업 상태가 있으면 시스템 프롬프트 뒤에 주입
        state_text = self.work_state.to_text()
        if state_text:
            msgs.append({"role": "user", "content": state_text})
            msgs.append({"role": "assistant", "content": '{"thought": "작업 상태를 확인했습니다.", "action": "answer", "arguments": {"text": "상태 확인 완료"}}'})

        msgs.extend(self.messages)
        return msgs

    def _trim(self):
        """대화가 너무 길면 오래된 턴부터 제거"""
        # 턴 수 제한
        while len(self.messages) > self.max_turns * 2:
            self.messages.pop(0)

        # 문자 수 제한
        total = sum(len(m["content"]) for m in self.messages)
        while total > self.max_chars and len(self.messages) > 2:
            removed = self.messages.pop(0)
            total -= len(removed["content"])

    def update_state(self, **kwargs):
        """작업 상태를 업데이트"""
        self.work_state.update_from_dict(kwargs)

    def reset(self):
        """대화 초기화"""
        self.messages.clear()
        self.work_state = WorkState()
        self.turn_count = 0
