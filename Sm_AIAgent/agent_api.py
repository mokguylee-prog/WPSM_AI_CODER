"""Agent API router for FastAPI (/agent endpoints)."""
from __future__ import annotations

import os
import json
import time
import queue
import threading
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from Sm_AIAgent.agent_loop import AgentLoop


def _dashboard_mod():
    """Find main api_server module to report request metrics."""
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


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


router = APIRouter(prefix="/agent", tags=["agent"])
_sessions: dict[str, AgentLoop] = {}
_session_cancel_flags: dict[str, bool] = {}
_session_last_seen: dict[str, float] = {}
_sessions_lock = threading.RLock()
SESSION_IDLE_TIMEOUT_S = 15 * 60
SESSION_SWEEP_INTERVAL_S = 60
_last_session_sweep = 0.0


class AgentRequest(BaseModel):
    message: str
    session_id: str = "default"
    working_dir: str = "."
    max_iterations: int = 15
    temperature: float = 0.1
    max_tokens: int = 1024


class ApprovalRequest(BaseModel):
    session_id: str = "default"
    command: str
    timeout: int = 30


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
    """Return existing agent session or create a new one."""
    steps = []

    def on_step(step):
        steps.append(step)

    now = time.time()
    with _sessions_lock:
        agent = _sessions.get(session_id)
        if agent is None:
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
            agent.on_step = on_step
            agent.max_iterations = max_iterations
            agent.temperature = temperature
            agent.max_tokens = max_tokens
            agent.working_dir = working_dir
        _session_cancel_flags.setdefault(session_id, False)
        _session_last_seen[session_id] = now

    return agent, steps


def _touch_session(session_id: str):
    with _sessions_lock:
        _session_last_seen[session_id] = time.time()


def _cleanup_expired_sessions():
    global _last_session_sweep
    now = time.time()
    if now - _last_session_sweep < SESSION_SWEEP_INTERVAL_S:
        return
    _last_session_sweep = now

    expired: list[str] = []
    with _sessions_lock:
        for sid, last_seen in list(_session_last_seen.items()):
            if now - last_seen > SESSION_IDLE_TIMEOUT_S:
                expired.append(sid)

        for sid in expired:
            agent = _sessions.pop(sid, None)
            _session_cancel_flags.pop(sid, None)
            _session_last_seen.pop(sid, None)
            if agent is not None:
                try:
                    agent.reset()
                except Exception:
                    pass


@router.post("/run", response_model=AgentResponse)
def agent_run(req: AgentRequest):
    """Run the agent loop and return final answer."""
    api_url = "http://localhost:8888"
    _cleanup_expired_sessions()

    agent, steps = _get_or_create_agent(
        session_id=req.session_id,
        api_url=api_url,
        working_dir=req.working_dir,
        max_iterations=req.max_iterations,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )

    entry = begin_request(req.message, kind="agent")
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
            _touch_session(req.session_id)
    except Exception as e:
        fail_request(entry, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"에이전트 실행 오류: {type(e).__name__}: {e}")

    finish_request(entry, _estimate_tokens(req.message), _estimate_tokens(answer), elapsed, answer)

    return AgentResponse(
        answer=answer,
        session_id=req.session_id,
        steps=steps,
        elapsed_ms=elapsed,
    )


@router.post("/stream")
def agent_stream(req: AgentRequest):
    """Run agent loop as NDJSON streaming response."""
    api_url = "http://localhost:8888"
    _cleanup_expired_sessions()

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

    entry = begin_request(req.message, kind="agent")

    def worker():
        original_dir = os.getcwd()
        t0 = time.time()
        try:
            if req.working_dir and os.path.isdir(req.working_dir):
                os.chdir(req.working_dir)
            answer = agent.run(req.message)
            elapsed = int((time.time() - t0) * 1000)
            finish_request(entry, _estimate_tokens(req.message), _estimate_tokens(answer), elapsed, answer)
            q.put(("final", {"answer": answer, "elapsed_ms": elapsed}))
        except Exception as e:
            fail_request(entry, f"{type(e).__name__}: {e}")
            q.put(("error", {"error": f"{type(e).__name__}: {e}"}))
        finally:
            try:
                os.chdir(original_dir)
            except Exception:
                pass
            _touch_session(req.session_id)
            q.put(_DONE)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        while True:
            if _session_cancel_flags.get(req.session_id):
                agent.cancel()
                _session_cancel_flags[req.session_id] = False
                yield json.dumps({"type": "error", "error": "cancelled"}, ensure_ascii=False) + "\n"
                break
            try:
                item = q.get(timeout=1.0)
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


@router.post("/cancel")
def agent_cancel(session_id: str = "default"):
    with _sessions_lock:
        _session_cancel_flags[session_id] = True
        agent = _sessions.get(session_id)
        _session_last_seen[session_id] = time.time()
    if agent is not None:
        agent.cancel()
    return {"status": "ok", "session_id": session_id}


@router.post("/approve")
def agent_approve(req: ApprovalRequest):
    """Re-run a blocked command after explicit user approval."""
    if not req.command.strip():
        raise HTTPException(400, "Command is required")
    from Sm_AIAgent.tools.registry import TOOL_REGISTRY

    run_result = TOOL_REGISTRY.execute(
        "run_command",
        {"command": req.command, "timeout": req.timeout, "allow_unsafe": True},
    )
    if not run_result["ok"]:
        raise HTTPException(400, str(run_result["error"]))

    return {
        "status": "ok",
        "session_id": req.session_id,
        "command": req.command,
        "result": run_result["result"],
    }


@router.post("/reset")
def agent_reset(session_id: str = "default"):
    """Reset a single agent session."""
    with _sessions_lock:
        agent = _sessions.pop(session_id, None)
        _session_cancel_flags.pop(session_id, None)
        _session_last_seen.pop(session_id, None)
    if agent is not None:
        agent.reset()
    return {"status": "ok", "session_id": session_id}


@router.get("/sessions")
def agent_sessions():
    """Return active sessions summary."""
    _cleanup_expired_sessions()
    now = time.time()
    with _sessions_lock:
        sessions = [
            {
                "session_id": sid,
                "turns": agent.context.turn_count,
                "goal": agent.context.work_state.goal,
                "last_seen_sec": round(now - _session_last_seen.get(sid, now), 1),
                "idle_timeout_sec": SESSION_IDLE_TIMEOUT_S,
            }
            for sid, agent in _sessions.items()
        ]
    return {
        "sessions": sessions,
        "session_idle_timeout_sec": SESSION_IDLE_TIMEOUT_S,
    }
