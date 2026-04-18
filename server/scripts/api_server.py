"""Sm_AICoder instruction-following API server (llama-cpp-python + GGUF)."""
import os
import glob
import time
import json
import traceback
import itertools
import queue
import threading
from typing import Optional
from collections import deque
from datetime import datetime

import sys

# Add project root to sys.path so local packages can be imported.
_PROJECT_ROOT_FOR_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT_FOR_PATH not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT_FOR_PATH)

try:
    from llama_cpp import Llama
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError as e:
    print(f"Install required packages: pip install llama-cpp-python fastapi uvicorn\n{e}")
    raise

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SERVER_DIR)
MODEL_DIR = os.path.join(PROJECT_ROOT, "Sm_AICoder", "models", "gguf")
LOG_DIR = os.path.join(SERVER_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, f"requests_{datetime.now().strftime('%Y%m%d%H%M%S')}.log")
REQUEST_SNAPSHOTS_DIR = os.path.join(LOG_DIR, "request_snapshots")
PORT = 8888
N_CTX = 8192
CTX_SAFETY_MARGIN = 256
N_THREADS = 8

# ---------------------------------------------------------------------------
# P5-1: N_GPU_LAYERS 자동 감지
#   우선순위: 환경변수 N_GPU_LAYERS > torch.cuda > nvidia-smi > CPU 폴백(0)
# ---------------------------------------------------------------------------

def _detect_gpu_layers() -> int:
    """Return optimal n_gpu_layers value based on detected hardware."""
    # 1) 환경변수 명시 지정이 최우선
    env_val = os.environ.get("N_GPU_LAYERS")
    if env_val is not None:
        try:
            layers = int(env_val)
            print(f"[GPU] N_GPU_LAYERS from env: {layers}")
            return layers
        except ValueError:
            print(f"[GPU] Invalid N_GPU_LAYERS env value '{env_val}', falling back to auto-detect")

    # 2) torch.cuda 확인 (torch 가 설치되어 있을 때만)
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
            print(f"[GPU] CUDA detected via torch: {gpu_name} ({vram_gb:.1f} GB VRAM)")
            print("[GPU] n_gpu_layers=-1 (full offload)")
            return -1
    except ImportError:
        pass

    # 3) nvidia-smi 확인 (torch 미설치 환경 대비)
    import subprocess
    _nvidia_smi_paths = [
        "nvidia-smi",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        r"C:\Windows\System32\nvidia-smi.exe",
    ]
    for smi_path in _nvidia_smi_paths:
        try:
            r = subprocess.run(
                [smi_path, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True,
                timeout=5,
            )
            if r.returncode == 0 and r.stdout:
                try:
                    out = r.stdout.decode("utf-8").strip()
                except UnicodeDecodeError:
                    out = r.stdout.decode("cp949", errors="replace").strip()
                if out:
                    print(f"[GPU] CUDA detected via nvidia-smi: {out.splitlines()[0]}")
                    print("[GPU] n_gpu_layers=-1 (full offload)")
                    return -1
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue

    # 4) GPU 없음 → CPU 전용
    print("[GPU] No CUDA GPU detected. Running CPU-only (n_gpu_layers=0)")
    return 0


N_GPU_LAYERS: int = _detect_gpu_layers()

# ---------------------------------------------------------------------------
# P5-2: 모델 라우팅 설정
#   model_route.first  — 첫 번째 사용자 턴에 사용할 모델 파일명 패턴 (큰 모델)
#   model_route.followup — 후속 도구 호출 턴에 사용할 모델 파일명 패턴 (작은 모델)
#   패턴이 None 이거나 파일이 없으면 단일 모델(find_model) 로 폴백한다.
# ---------------------------------------------------------------------------

MODEL_ROUTE: dict = {
    "first": os.environ.get("MODEL_ROUTE_FIRST", "qwen2.5-coder-7b"),
    "followup": os.environ.get("MODEL_ROUTE_FOLLOWUP", "qwen2.5-coder-1.5b"),
}

# P5-3: KV 캐시 재사용 — 시스템 프롬프트/도구 스키마가 변하지 않으므로 True
CACHE_PROMPT: bool = os.environ.get("CACHE_PROMPT", "1").strip().lower() not in ("0", "false", "no")

SYSTEM_PROMPT = (
    "You are an expert C/C++ programming assistant. "
    "When the user asks you to write code, provide complete, working code. "
    "When creating project files, show the full file contents. "
    "When the request is to create an example or a project, always respond with file-separated output. "
    "Use this format for every file: a clear file path line such as 'File: path/to/file.ext' "
    "followed by a fenced code block containing only that file's contents. "
    "For multi-file projects, emit one section per file and do not mix unrelated files in one block. "
    "If you generate C# WinForms examples, include each file separately, such as Program.cs, Form1.cs, "
    "Form1.Designer.cs, and the .csproj file. "
    "Respond in the same language the user writes in (Korean if Korean, English if English). "
    "Keep explanations concise unless asked for details."
)

app = FastAPI(title="Sm_AICoder Instruction API")

try:
    from Sm_AIAgent.agent_api import router as agent_router

    app.include_router(agent_router)
    print("[Sm_AIAgent] Agent router registered (/agent/*)")
except ImportError as _agent_err:
    print(f"[Sm_AIAgent] Agent module load failed (chat-only mode): {_agent_err}")

# P5-2: 라우팅 모델 인스턴스
#   llm        — primary (첫 턴 / 단일 모드)
#   llm_small  — followup 도구 호출용 경량 모델 (None 이면 llm 으로 폴백)
llm: Optional[Llama] = None
llm_small: Optional[Llama] = None
model_name: str = ""
model_name_small: str = ""
start_time: float = 0.0

stats = {
    "total_requests": 0,
    "total_prompt_tokens": 0,
    "total_generated_tokens": 0,
    "total_elapsed_ms": 0.0,
}
recent_requests: deque = deque(maxlen=20)
_req_counter = itertools.count(1)


def write_log(entry: dict):
    os.makedirs(LOG_DIR, exist_ok=True)
    clean = {k: v for k, v in entry.items() if not k.startswith("_")}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(clean, ensure_ascii=False) + "\n")


def begin_request(prompt: str, kind: str = "chat") -> dict:
    """Create pending request row for dashboard."""
    entry = {
        "id": next(_req_counter),
        "kind": kind,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "prompt": prompt,
        "response": "",
        "prompt_tokens": 0,
        "gen_tokens": 0,
        "elapsed_ms": 0,
        "status": "pending",
        "_t0": time.time(),
    }
    recent_requests.appendleft(entry)
    return entry


def finish_request(entry: dict, prompt_tokens: int, gen_tokens: int, elapsed_ms: float, response: str):
    prompt_tokens = int(prompt_tokens or 0)
    gen_tokens = int(gen_tokens or 0)
    entry["prompt_tokens"] = prompt_tokens
    entry["gen_tokens"] = gen_tokens
    entry["elapsed_ms"] = round(elapsed_ms)
    entry["response"] = response
    entry["status"] = "done"

    stats["total_requests"] += 1
    stats["total_prompt_tokens"] += prompt_tokens
    stats["total_generated_tokens"] += gen_tokens
    stats["total_elapsed_ms"] += elapsed_ms

    write_log(entry)


def fail_request(entry: dict, err: str):
    entry["status"] = "error"
    entry["response"] = f"[error] {err}"
    entry["elapsed_ms"] = round((time.time() - entry.get("_t0", time.time())) * 1000)
    write_log(entry)


def _count_messages_tokens(messages: list[dict]) -> int:
    if llm is None:
        return 0
    try:
        text = "\n".join(m.get("content", "") for m in messages)
        return len(llm.tokenize(text.encode("utf-8"), add_bos=False))
    except Exception:
        return sum(len(m.get("content", "")) // 3 for m in messages)


def _clamp_max_tokens(messages: list[dict], requested: int) -> int:
    prompt_tokens = _count_messages_tokens(messages)
    budget = N_CTX - prompt_tokens - CTX_SAFETY_MARGIN
    if budget <= 64:
        raise HTTPException(
            400,
            f"Context window exceeded: prompt={prompt_tokens} tok / n_ctx={N_CTX}. "
            "Start a new chat or reduce previous context.",
        )
    if requested > budget:
        print(f"[guard] max_tokens {requested} -> {budget} (prompt={prompt_tokens})")
        return budget
    return requested


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def find_model(pattern: Optional[str] = None) -> str:
    """Return path to best matching GGUF model.

    Args:
        pattern: Optional substring to match against filenames (case-insensitive).
                 When None or no match found, returns the largest GGUF file.
    """
    files = glob.glob(os.path.join(MODEL_DIR, "*.gguf"))
    if not files:
        raise FileNotFoundError(
            f"No GGUF model found: {MODEL_DIR}\n"
            "Run: python server/scripts/download_model.py"
        )
    if pattern:
        pattern_lower = pattern.lower()
        matched = [f for f in files if pattern_lower in os.path.basename(f).lower()]
        if matched:
            return max(matched, key=os.path.getsize)
        print(f"[ModelRoute] Pattern '{pattern}' not matched in {MODEL_DIR}. Falling back to largest model.")
    return max(files, key=os.path.getsize)


def _load_llama(path: str, label: str = "") -> Llama:
    """Instantiate a Llama model with shared server settings."""
    tag = f"[{label}] " if label else ""
    print(f"{tag}Loading model: {os.path.basename(path)} | n_gpu_layers={N_GPU_LAYERS} | cache_prompt={CACHE_PROMPT}")
    return Llama(
        model_path=path,
        n_ctx=N_CTX,
        n_threads=N_THREADS,
        n_gpu_layers=N_GPU_LAYERS,
        verbose=False,
    )


# ---------------------------------------------------------------------------
# P5-2: 라우팅 헬퍼 — turn_index 0 이면 big model, 1+ 이면 small model
# ---------------------------------------------------------------------------

def _route_llm(turn_index: int = 0) -> Llama:
    """Return appropriate Llama instance based on conversation turn."""
    if turn_index > 0 and llm_small is not None:
        return llm_small
    return llm  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# P5-3: prompt cache env flag helper
# ---------------------------------------------------------------------------

def _chat_kwargs(base: dict) -> dict:
    """Return chat kwargs compatible with the installed llama-cpp-python version."""
    return base


def _create_chat_completion_safe(llm_obj: Llama, kwargs: dict):
    """Call create_chat_completion with a compatibility fallback for older builds."""
    return llm_obj.create_chat_completion(**kwargs)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    max_tokens: int = 1024
    temperature: float = 0.3
    top_p: float = 0.95
    force_json: bool = False
    # P5-2: 0 = 첫 턴 (big model), 1+ = 후속 도구 호출 턴 (small model)
    turn_index: int = 0


class ChatStreamRequest(BaseModel):
    messages: list[ChatMessage]
    max_tokens: int = 1024
    temperature: float = 0.3
    top_p: float = 0.95
    # P5-2: 0 = 첫 턴, 1+ = 후속 도구 호출 턴
    turn_index: int = 0
    # P6-3: 호출 출처를 대시보드에 기록. "chat"(기본) 또는 "agent-step".
    kind: str = "chat"


class GenerateRequest(BaseModel):
    prompt: str
    system: str = SYSTEM_PROMPT
    max_tokens: int = 1024
    temperature: float = 0.3
    top_p: float = 0.95


class GenerateResponse(BaseModel):
    generated: str
    model: str
    prompt_tokens: int
    generated_tokens: int


@app.on_event("startup")
def load_model():
    """P5-1/P5-2/P5-3: GPU auto-detect, model routing, prompt cache flag."""
    global llm, llm_small, model_name, model_name_small, start_time

    # Primary (big) model — 첫 턴 / 단일 모드
    first_pattern = MODEL_ROUTE.get("first")
    primary_path = find_model(first_pattern)
    model_name = os.path.basename(primary_path)
    llm = _load_llama(primary_path, label="primary")
    print(f"[primary] Model ready: {model_name}")

    # Followup (small) model — 도구 호출 후속 턴 (선택적)
    followup_pattern = MODEL_ROUTE.get("followup")
    if followup_pattern:
        followup_path = find_model(followup_pattern)
        followup_basename = os.path.basename(followup_path)
        # 큰 모델과 같은 파일이면 별도 로드 불필요
        if followup_path != primary_path:
            llm_small = _load_llama(followup_path, label="followup")
            model_name_small = followup_basename
            print(f"[followup] Model ready: {model_name_small}")
        else:
            print(f"[followup] Same as primary ({followup_basename}). Single-model mode.")
            model_name_small = model_name

    start_time = time.time()
    print(f"Server startup complete | GPU layers={N_GPU_LAYERS} | cache_prompt={CACHE_PROMPT}")


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    if llm is None:
        raise HTTPException(503, "Model is loading")

    messages = [{"role": "system", "content": req.system}, {"role": "user", "content": req.prompt}]
    entry = begin_request(req.prompt, kind="generate")

    try:
        max_tokens = _clamp_max_tokens(messages, req.max_tokens)
        t0 = time.time()
        # P5-2: /generate 는 항상 첫 턴(big model)
        # P5-3: prompt cache flag is logged but not passed to create_chat_completion
        result = _create_chat_completion_safe(_route_llm(0), _chat_kwargs(dict(
            messages=messages,
            max_tokens=max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
        )))
        elapsed = (time.time() - t0) * 1000

        choice = result["choices"][0]
        usage = result.get("usage", {})
        pt = usage.get("prompt_tokens", 0)
        gt = usage.get("completion_tokens", 0)
        response_text = choice["message"]["content"]

        finish_request(entry, pt, gt, elapsed, response_text)
        return GenerateResponse(generated=response_text, model=model_name, prompt_tokens=pt, generated_tokens=gt)
    except HTTPException as e:
        fail_request(entry, e.detail if isinstance(e.detail, str) else str(e.detail))
        raise
    except Exception as e:
        traceback.print_exc()
        fail_request(entry, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"Generation failed: {type(e).__name__}: {e}")


@app.post("/chat")
def chat(req: ChatRequest):
    if llm is None:
        raise HTTPException(503, "Model is loading")

    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

    user_msgs = [m.content for m in req.messages if m.role == "user"]
    entry = begin_request(user_msgs[-1] if user_msgs else "", kind="chat")

    try:
        max_tokens = _clamp_max_tokens(messages, req.max_tokens)
        t0 = time.time()

        # P3-1: force_json=True 이면 GBNF json_object 그래머로 모델 출력 강제.
        # llama-cpp-python 0.3.x 에서 response_format={"type":"json_object"} 가
        # GBNF 그래머로 동작하므로 생성 속도가 약간 낮아질 수 있음 — 옵션으로만 사용.
        call_kwargs: dict = dict(
            messages=messages,
            max_tokens=max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
        )

        if req.force_json:
            call_kwargs["response_format"] = {"type": "json_object"}

        # P5-2: turn_index 로 big/small 모델 선택
        # P5-3: prompt cache flag is logged but not passed to create_chat_completion
        active_llm = _route_llm(req.turn_index)
        active_model_name = model_name_small if (active_llm is llm_small and llm_small is not None) else model_name
        result = _create_chat_completion_safe(active_llm, _chat_kwargs(call_kwargs))
        elapsed = (time.time() - t0) * 1000

        choice = result["choices"][0]
        usage = result.get("usage", {})
        pt = usage.get("prompt_tokens", 0)
        gt = usage.get("completion_tokens", 0)
        response_text = choice["message"]["content"]

        finish_request(entry, pt, gt, elapsed, response_text)
        return {
            "response": response_text,
            "elapsed_ms": round(elapsed),
            "message": choice["message"],
            "model": active_model_name,
            "usage": usage,
        }
    except HTTPException as e:
        fail_request(entry, e.detail if isinstance(e.detail, str) else str(e.detail))
        raise
    except Exception as e:
        traceback.print_exc()
        fail_request(entry, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"Generation failed: {type(e).__name__}: {e}")


@app.post("/chat/stream")
def chat_stream(req: ChatStreamRequest):
    """NDJSON 스트리밍 /chat 엔드포인트.

    P4-2: idle-timeout — 마지막 토큰 이후 IDLE_TIMEOUT_S 초 무응답 시 연결을 끊는다.
          300s 단일 timeout 방식은 폐기되었다.
    """
    if llm is None:
        raise HTTPException(503, "Model is loading")

    # P4-2: idle-timeout 상수 — AgentLoop.IDLE_TIMEOUT_S 와 동일 값 사용
    IDLE_TIMEOUT_S: float = 60.0

    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

    user_msgs = [m.content for m in req.messages if m.role == "user"]
    # P6-3: 요청자가 kind 를 지정한 경우("agent-step") 그대로 기록한다.
    entry = begin_request(user_msgs[-1] if user_msgs else "", kind=req.kind)
    q: "queue.Queue[object]" = queue.Queue()
    done = object()

    def worker():
        try:
            max_tokens = _clamp_max_tokens(messages, req.max_tokens)
            t0 = time.time()
            chunks = []
            # P5-2: turn_index 로 big/small 모델 선택
            # P5-3: prompt cache flag is logged but not passed to create_chat_completion
            active_llm = _route_llm(req.turn_index)
            stream = _create_chat_completion_safe(
                active_llm,
                _chat_kwargs(dict(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=req.temperature,
                    top_p=req.top_p,
                    stream=True,
                )),
            )
            for piece in stream:
                delta = piece["choices"][0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    chunks.append(token)
                    q.put({"type": "token", "text": token})
            elapsed = (time.time() - t0) * 1000
            response_text = "".join(chunks)
            pt = _count_messages_tokens(messages)
            gt = _estimate_tokens(response_text)
            finish_request(entry, pt, gt, elapsed, response_text)
            q.put({"type": "final", "response": response_text, "elapsed_ms": round(elapsed)})
        except Exception as e:
            traceback.print_exc()
            fail_request(entry, f"{type(e).__name__}: {e}")
            q.put({"type": "error", "error": f"{type(e).__name__}: {e}"})
        finally:
            q.put(done)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        last_activity = time.monotonic()  # P4-2: idle-timeout 기준점
        while True:
            try:
                item = q.get(timeout=1.0)
                last_activity = time.monotonic()  # 데이터 수신 → 리셋
            except queue.Empty:
                # P4-2: idle-timeout 검사
                idle = time.monotonic() - last_activity
                if idle > IDLE_TIMEOUT_S:
                    yield json.dumps(
                        {"type": "error", "error": f"idle_timeout after {idle:.0f}s"},
                        ensure_ascii=False,
                    ) + "\n"
                    break
                yield json.dumps({"type": "heartbeat", "ts": time.time()}, ensure_ascii=False) + "\n"
                continue
            if item is done:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/health")
def health():
    return {"status": "ok", "model": model_name}


@app.get("/stats")
def get_stats():
    uptime = int(time.time() - start_time) if start_time else 0
    avg_ms = stats["total_elapsed_ms"] / stats["total_requests"] if stats["total_requests"] > 0 else 0

    items = []
    now = time.time()
    for r in recent_requests:
        item = {
            "time": r["time"],
            "prompt": r["prompt"],
            "response": r["response"],
            "prompt_tokens": r["prompt_tokens"],
            "gen_tokens": r["gen_tokens"],
            "elapsed_ms": r["elapsed_ms"],
            "status": r.get("status", "done"),
            "kind": r.get("kind", "chat"),
        }
        if item["status"] == "pending":
            item["elapsed_ms"] = round((now - r.get("_t0", now)) * 1000)
        items.append(item)

    return {
        "model": model_name,
        "uptime_sec": uptime,
        "total_requests": stats["total_requests"],
        "total_prompt_tokens": stats["total_prompt_tokens"],
        "total_generated_tokens": stats["total_generated_tokens"],
        "avg_response_ms": round(avg_ms),
        "recent": items,
    }


@app.get("/logs/download")
def download_log():
    if not os.path.exists(LOG_FILE):
        raise HTTPException(404, "Log file not found")
    download_name = f"requests_{datetime.now().strftime('%Y%m%d%H%M%S')}.log"
    return FileResponse(LOG_FILE, filename=download_name, media_type="text/plain; charset=utf-8")


@app.post("/requests/{request_index}/save")
def save_request_snapshot(request_index: int):
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    if request_index < 0 or request_index >= len(recent_requests):
        raise HTTPException(404, "Request not found")

    req = list(recent_requests)[request_index]
    stamp = req.get("time", now).replace("-", "").replace(":", "").replace(" ", "_")
    safe_kind = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(req.get("kind", "chat")))
    folder_name = f"{stamp}_{safe_kind}"
    folder_path = os.path.join(REQUEST_SNAPSHOTS_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    md_path = os.path.join(folder_path, "request.md")
    json_path = os.path.join(folder_path, "request.json")

    md_text = (
        f"# Request Snapshot\n\n"
        f"- Time: {req.get('time', '')}\n"
        f"- Kind: {req.get('kind', '')}\n"
        f"- Status: {req.get('status', '')}\n"
        f"- Prompt tokens: {req.get('prompt_tokens', 0)}\n"
        f"- Gen tokens: {req.get('gen_tokens', 0)}\n"
        f"- Elapsed: {req.get('elapsed_ms', 0)} ms\n\n"
        f"## Prompt\n\n{req.get('prompt', '')}\n\n"
        f"## Response\n\n{req.get('response', '')}\n"
    )
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(md_text)
    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(req, f, ensure_ascii=False, indent=2)

    return {
        "saved": True,
        "folder": folder_path,
        "files": [md_path, json_path],
    }


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(DASHBOARD_HTML)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sm_AICoder Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0d1117; color: #c9d1d9; font-family: 'Segoe UI', sans-serif; padding: 24px; }
  h1 { font-size: 1.4rem; color: #58a6ff; margin-bottom: 4px; }
  .subtitle { font-size: 0.85rem; color: #6e7681; margin-bottom: 24px; }
  .status-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 24px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: #3fb950; box-shadow: 0 0 6px #3fb950; animation: pulse 2s infinite; }
  .dot.offline { background: #f85149; box-shadow: 0 0 6px #f85149; animation: none; }
  @keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: 0.4 } }
  .status-text { font-size: 0.9rem; color: #8b949e; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 28px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 16px 20px; }
  .card-label { font-size: 0.75rem; color: #6e7681; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }
  .card-value { font-size: 1.6rem; font-weight: 700; color: #e6edf3; }
  .card-value.blue { color: #58a6ff; }
  .card-value.green { color: #3fb950; }
  .card-value.yellow { color: #d29922; }
  .card-value.purple { color: #bc8cff; }
  .model-box { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 14px 20px; margin-bottom: 28px; font-size: 0.9rem; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }
  .model-box span { color: #58a6ff; font-weight: 600; }
  .btn-log { background: #21262d; border: 1px solid #30363d; color: #8b949e; padding: 6px 14px; border-radius: 6px; font-size: 0.8rem; cursor: pointer; text-decoration: none; }
  .btn-log:hover { background: #30363d; color: #c9d1d9; }
  .section-title { font-size: 0.95rem; color: #8b949e; margin-bottom: 12px; border-bottom: 1px solid #21262d; padding-bottom: 8px; }
  table { width: 100%; border-collapse: collapse; background: #161b22; border: 1px solid #30363d; border-radius: 10px; overflow: hidden; font-size: 0.82rem; }
  th { background: #21262d; color: #6e7681; text-align: left; padding: 10px 14px; font-weight: 600; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.05em; }
  td { padding: 9px 14px; border-top: 1px solid #21262d; color: #c9d1d9; }
  tr.clickable { cursor: pointer; }
  tr.clickable:hover td { background: #1c2128; }
  tr.pending td { background: #1e1a0a; }
  tr.pending:hover td { background: #2a230d; }
  tr.error td { background: #2a1414; }
  tr.error:hover td { background: #3a1a1a; }
  .prompt-cell { color: #8b949e; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .status-badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:0.72rem; font-weight:600; margin-right:6px; }
  .status-pending { background:#3d2e0a; color:#d29922; animation: blink 1.2s infinite; }
  .status-error { background:#2a1414; color:#f85149; }
  @keyframes blink { 0%,100% { opacity: 1 } 50% { opacity: 0.55 } }
  .refresh-info { font-size: 0.75rem; color: #484f58; margin-top: 16px; text-align: right; }
  .modal-bg { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.7); z-index:100; justify-content:center; align-items:center; }
  .modal-bg.show { display:flex; }
  .modal { background:#161b22; border:1px solid #30363d; border-radius:12px; width:min(800px,95vw); max-height:85vh; overflow:hidden; display:flex; flex-direction:column; }
  .modal-header { padding:16px 20px; border-bottom:1px solid #21262d; display:flex; justify-content:space-between; align-items:center; }
  .modal-header h3 { color:#58a6ff; font-size:1rem; }
  .modal-close { background:none; border:none; color:#6e7681; font-size:1.4rem; cursor:pointer; line-height:1; }
  .modal-close:hover { color:#c9d1d9; }
  .modal-body { padding:20px; overflow-y:auto; display:flex; flex-direction:column; gap:16px; }
  .modal-section label { font-size:0.72rem; color:#6e7681; text-transform:uppercase; letter-spacing:0.05em; display:block; margin-bottom:6px; }
  .modal-section pre { background:#0d1117; border:1px solid #21262d; border-radius:8px; padding:12px 14px; font-size:0.82rem; white-space:pre-wrap; word-break:break-word; color:#c9d1d9; max-height:220px; overflow-y:auto; line-height:1.5; }
  .modal-meta { display:flex; gap:16px; flex-wrap:wrap; }
  .meta-chip { background:#21262d; border-radius:6px; padding:4px 10px; font-size:0.78rem; color:#8b949e; }
  .meta-chip span { color:#e6edf3; font-weight:600; }
</style>
</head>
<body>
<h1>Sm_AICoder Dashboard</h1>
<p class="subtitle">Instruction-Following Code Generation Server</p>

<div class="status-bar">
  <div class="dot" id="dot"></div>
  <span class="status-text" id="status-text">Checking connection...</span>
</div>

<div class="model-box">
  <div>Model: <span id="model-name">Loading...</span> &nbsp;|&nbsp; Uptime: <span id="uptime">-</span></div>
  <a class="btn-log" href="/logs/download" download>Download Logs</a>
</div>

<div class="cards">
  <div class="card"><div class="card-label">Total Requests</div><div class="card-value blue" id="total-req">-</div></div>
  <div class="card"><div class="card-label">Generated Tokens</div><div class="card-value green" id="total-gen">-</div></div>
  <div class="card"><div class="card-label">Prompt Tokens</div><div class="card-value yellow" id="total-prompt">-</div></div>
  <div class="card"><div class="card-label">Average Response</div><div class="card-value purple" id="avg-ms">-</div></div>
</div>

<div class="section-title">Recent Requests (up to 20, click a row for details)</div>
<table>
  <thead>
    <tr>
      <th>Time</th>
      <th>Prompt</th>
      <th>Prompt Tokens</th>
      <th>Gen Tokens</th>
      <th>Elapsed</th>
      <th>Kind</th>
    </tr>
  </thead>
  <tbody id="req-tbody">
    <tr><td colspan="6" style="color:#484f58;text-align:center;padding:20px">No requests yet</td></tr>
  </tbody>
</table>
<p class="refresh-info">Auto refresh every 2 seconds &nbsp;|&nbsp; <span id="last-update">-</span></p>

<div class="modal-bg" id="modal-bg" onclick="closeModal(event)">
  <div class="modal">
    <div class="modal-header">
      <h3 id="modal-time">Request Details</h3>
      <button class="modal-close" onclick="closeModal()">&#x2715;</button>
    </div>
    <div class="modal-body">
      <div class="modal-meta" id="modal-meta"></div>
      <div class="modal-section"><label>Prompt</label><pre id="modal-prompt"></pre></div>
      <div class="modal-section"><label>Response</label><pre id="modal-response"></pre></div>
    </div>
  </div>
</div>

<script>
let recentData = [];

function fmtUptime(sec) {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  if (h > 0) return h + 'h ' + m + 'm';
  if (m > 0) return m + 'm ' + s + 's';
  return s + 's';
}

function fmtDurationMs(ms) {
  const value = Number(ms) || 0;
  if (value >= 1000) {
    return (value / 1000).toFixed(1).replace(/\\.0$/, '') + ' sec';
  }
  return Math.round(value) + ' ms';
}

function fmtNumber(value) {
  const n = Number(value || 0);
  if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\\.0$/, '') + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\\.0$/, '') + 'k';
  return n.toLocaleString();
}

function openModal(idx) {
  const r = recentData[idx];
  if (!r) return;
  document.getElementById('modal-time').textContent = r.time + ' - Request Details';
  document.getElementById('modal-prompt').textContent = r.prompt;
  document.getElementById('modal-response').textContent = r.response;
  document.getElementById('modal-meta').innerHTML =
    `<div class="meta-chip">Kind <span>${r.kind || 'chat'}</span></div>
     <div class="meta-chip">Prompt Tokens <span>${fmtNumber(r.prompt_tokens)}</span></div>
     <div class="meta-chip">Generated Tokens <span>${fmtNumber(r.gen_tokens)}</span></div>
     <div class="meta-chip">Elapsed <span>${fmtDurationMs(r.elapsed_ms)}</span></div>`;
  document.getElementById('modal-bg').classList.add('show');
  saveRequestSnapshot(idx);
}

async function saveRequestSnapshot(idx) {
  try {
    const r = await fetch(`/requests/${idx}/save`, { method: 'POST' });
    if (!r.ok) return;
    const d = await r.json();
    document.getElementById('last-update').textContent =
      'Saved snapshot: ' + (d.folder || '-');
  } catch (e) {
    // Ignore save failures so the dashboard stays usable.
  }
}

function closeModal(e) {
  if (!e || e.target === document.getElementById('modal-bg') || e.target.classList.contains('modal-close')) {
    document.getElementById('modal-bg').classList.remove('show');
  }
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.getElementById('modal-bg').classList.remove('show');
});

async function refresh() {
  try {
    const r = await fetch('/health');
    if (!r.ok) throw new Error('health failed');
    const d = await r.json();
    document.getElementById('dot').className = 'dot';
    document.getElementById('status-text').textContent = 'Online';
    document.getElementById('model-name').textContent = d.model || '-';
    document.getElementById('uptime').textContent = fmtUptime(d.uptime_sec);
  } catch (e) {
    document.getElementById('dot').className = 'dot offline';
    document.getElementById('status-text').textContent = 'Offline';
    return;
  }

  try {
    const stats = await fetch('/stats');
    if (!stats.ok) throw new Error('stats failed');
    const d = await stats.json();
    document.getElementById('total-req').textContent = fmtNumber(d.total_requests);
    document.getElementById('total-gen').textContent = fmtNumber(d.total_generated_tokens);
    document.getElementById('total-prompt').textContent = fmtNumber(d.total_prompt_tokens);
    document.getElementById('avg-ms').textContent = d.total_requests > 0 ? fmtDurationMs(d.avg_response_ms) : '-';

    recentData = d.recent || [];
    const tbody = document.getElementById('req-tbody');

    if (recentData.length > 0) {
      tbody.innerHTML = recentData.map((r, i) => {
        const status = r.status || 'done';
        const rowCls = status === 'pending' ? 'clickable pending' : (status === 'error' ? 'clickable error' : 'clickable');
        const badge = status === 'pending'
          ? '<span class="status-badge status-pending">Pending</span>'
          : (status === 'error' ? '<span class="status-badge status-error">Error</span>' : '');
        const elapsed = status === 'pending' ? `${fmtDurationMs(r.elapsed_ms)} elapsed...` : fmtDurationMs(r.elapsed_ms);
        const ptCell = status === 'pending' ? '-' : fmtNumber(r.prompt_tokens);
        const gtCell = status === 'pending' ? '-' : fmtNumber(r.gen_tokens);
        const safePrompt = r.prompt.replace(/"/g, '&quot;');
        const kind = r.kind || 'chat';
        const kindColor = kind === 'agent-step' ? '#bc8cff'
          : kind === 'agent' ? '#d29922'
          : '#3fb950';
        const kindCell = `<span style="color:${kindColor};font-weight:600;font-size:0.78rem">${kind}</span>`;

        return `
        <tr class="${rowCls}" onclick="openModal(${i})">
          <td>${r.time.split(' ')[1]}</td>
          <td class="prompt-cell" title="${safePrompt}">${badge}${r.prompt.substring(0,60)}${r.prompt.length > 60 ? '...' : ''}</td>
          <td>${ptCell}</td>
          <td>${gtCell}</td>
          <td>${elapsed}</td>
          <td>${kindCell}</td>
        </tr>`;
      }).join('');
    } else {
      tbody.innerHTML = '<tr><td colspan="6" style="color:#484f58;text-align:center;padding:20px">No requests yet</td></tr>';
    }

    document.getElementById('last-update').textContent = 'Last update: ' + new Date().toLocaleTimeString();
  } catch (e) {
    document.getElementById('last-update').textContent = 'Stats unavailable';
  }
}

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    print(f"Sm_AICoder API server: http://localhost:{PORT}")
    print(f"Dashboard: http://localhost:{PORT}/")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
