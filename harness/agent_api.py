"""에이전트 API — FastAPI 라우터로 /agent 엔드포인트 제공

기존 api_server.py의 /chat을 백엔드로 활용하되,
에이전트 루프(도구 호출 → 결과 피드백 → 재판단)를 서버 측에서 실행합니다.
"""
from __future__ import annotations
import os
import json
import time
import queue
import threading
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from harness.agent_loop import AgentLoop


def _dashboard_mod():
    """api_server 모듈을 런타임에 찾아 반환 (import 순환 회피)."""
    import sys
    for name in ("__main__", "scripts.api_server", "server.scripts.api_server", "api_server"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "begin_request"):
            return mod
    return None


def begin_request(prompt: str, kind: str = "agent"):
    mod = _dashboard_mod()
    if mod:
        return mod.begin_request(prompt, kind)
    return None


def finish_request(entry, prompt_tokens, gen_tokens, elapsed_ms, response):
    if entry is None:
        return
    mod = _dashboard_mod()
    if mod:
        mod.finish_request(entry, prompt_tokens, gen_tokens, elapsed_ms, response)


def fail_request(entry, err: str):
    if entry is None:
        return
    mod = _dashboard_mod()
    if mod:
        mod.fail_request(entry, err)


router = APIRouter(prefix="/agent", tags=["agent"])

# 세션별 에이전트 인스턴스 관리
_sessions: dict[str, AgentLoop] = {}


class AgentRequest(BaseModel):
    message: str
    session_id: str = "default"
    working_dir: str = "."
    max_iterations: int = 15
    temperature: float = 0.1
    max_tokens: int = 1024


class AgentResponse(BaseModel):
    answer: str
    session_id: str
    steps: list[dict]
    elapsed_ms: int


def _get_or_create_agent(
    session_id: str,
    api_url: str,
    working_dir: str,
    max_iterations: int,
    temperature: float,
    max_tokens: int,
) -> tuple[AgentLoop, list[dict]]:
    """세션별 에이전트를 가져오거나 생성"""
    steps = []

    def on_step(step):
        steps.append(step)

    if session_id not in _sessions:
        agent = AgentLoop(
            api_url=api_url,
            max_iterations=max_iterations,
            temperature=temperature,
            max_tokens=max_tokens,
            working_dir=working_dir,
            on_step=on_step,
        )
        _sessions[session_id] = agent
    else:
        agent = _sessions[session_id]
        agent.on_step = on_step
        agent.max_iterations = max_iterations
        agent.temperature = temperature
        agent.max_tokens = max_tokens

    return agent, steps


@router.post("/run", response_model=AgentResponse)
def agent_run(req: AgentRequest):
    """에이전트 루프를 실행하고 최종 답변을 반환"""
    # 자기 자신의 /chat을 사용 (같은 서버)
    api_url = "http://localhost:8888"

    agent, steps = _get_or_create_agent(
        session_id=req.session_id,
        api_url=api_url,
        working_dir=req.working_dir,
        max_iterations=req.max_iterations,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )

    # 대시보드에 즉시 pending 등록
    entry = begin_request(req.message, kind="agent")

    # 작업 디렉토리 변경
    original_dir = os.getcwd()
    try:
        try:
            if req.working_dir and os.path.isdir(req.working_dir):
                os.chdir(req.working_dir)

            t0 = time.time()
            answer = agent.run(req.message)
            elapsed = int((time.time() - t0) * 1000)
        finally:
            os.chdir(original_dir)
    except Exception as e:
        fail_request(entry, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"에이전트 실행 오류: {type(e).__name__}: {e}")

    finish_request(entry, 0, 0, elapsed, answer)

    return AgentResponse(
        answer=answer,
        session_id=req.session_id,
        steps=steps,
        elapsed_ms=elapsed,
    )


@router.post("/stream")
def agent_stream(req: AgentRequest):
    """에이전트 루프를 스트리밍으로 실행 — NDJSON 한 줄씩 이벤트 송출.

    이벤트 종류:
      - step    : {"type":"step", "step": {...}}           (thinking/action/tool_result/...)
      - heartbeat: {"type":"heartbeat", "ts": ...}          (2초마다, 연결 생존 확인용)
      - final   : {"type":"final", "answer": "...", "elapsed_ms": N}
      - error   : {"type":"error", "error": "..."}
    """
    api_url = "http://localhost:8888"

    q: "queue.Queue[object]" = queue.Queue()
    _DONE = object()

    def on_step(step):
        q.put(("step", step))

    agent, _ = _get_or_create_agent(
        session_id=req.session_id,
        api_url=api_url,
        working_dir=req.working_dir,
        max_iterations=req.max_iterations,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )
    agent.on_step = on_step

    # 대시보드에 즉시 pending 등록
    entry = begin_request(req.message, kind="agent")

    def worker():
        original_dir = os.getcwd()
        t0 = time.time()
        try:
            if req.working_dir and os.path.isdir(req.working_dir):
                os.chdir(req.working_dir)
            answer = agent.run(req.message)
            elapsed = int((time.time() - t0) * 1000)
            finish_request(entry, 0, 0, elapsed, answer)
            q.put(("final", {"answer": answer, "elapsed_ms": elapsed}))
        except Exception as e:
            fail_request(entry, f"{type(e).__name__}: {e}")
            q.put(("error", {"error": f"{type(e).__name__}: {e}"}))
        finally:
            try:
                os.chdir(original_dir)
            except Exception:
                pass
            q.put(_DONE)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        while True:
            try:
                item = q.get(timeout=2.0)
            except queue.Empty:
                yield json.dumps({"type": "heartbeat", "ts": time.time()}, ensure_ascii=False) + "\n"
                continue
            if item is _DONE:
                break
            kind, payload = item
            if kind == "step":
                yield json.dumps({"type": "step", "step": payload}, ensure_ascii=False) + "\n"
            elif kind == "final":
                yield json.dumps({"type": "final", **payload}, ensure_ascii=False) + "\n"
            elif kind == "error":
                yield json.dumps({"type": "error", **payload}, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.post("/reset")
def agent_reset(session_id: str = "default"):
    """세션 초기화"""
    if session_id in _sessions:
        _sessions[session_id].reset()
        del _sessions[session_id]
    return {"status": "ok", "session_id": session_id}


@router.get("/sessions")
def agent_sessions():
    """활성 세션 목록"""
    return {
        "sessions": [
            {
                "session_id": sid,
                "turns": agent.context.turn_count,
                "goal": agent.context.work_state.goal,
            }
            for sid, agent in _sessions.items()
        ]
    }
