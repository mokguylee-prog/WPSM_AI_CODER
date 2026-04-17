"""Sm_AICoder instruction-following API server (llama-cpp-python + GGUF)."""
import os
import glob
import time
import json
import traceback
import itertools
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
    from fastapi.responses import HTMLResponse, FileResponse
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
PORT = 8888
N_CTX = 8192
CTX_SAFETY_MARGIN = 256
N_THREADS = 8
N_GPU_LAYERS = 0

SYSTEM_PROMPT = (
    "You are an expert C/C++ programming assistant. "
    "When the user asks you to write code, provide complete, working code. "
    "When creating project files, show the full file contents. "
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

llm: Optional[Llama] = None
model_name: str = ""
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


def find_model() -> str:
    files = glob.glob(os.path.join(MODEL_DIR, "*.gguf"))
    if not files:
        raise FileNotFoundError(
            f"No GGUF model found: {MODEL_DIR}\n"
            "Run: python server/scripts/download_model.py"
        )
    return max(files, key=os.path.getsize)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    max_tokens: int = 1024
    temperature: float = 0.3
    top_p: float = 0.95


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
    global llm, model_name, start_time
    path = find_model()
    model_name = os.path.basename(path)
    print(f"Loading model: {model_name}")
    llm = Llama(model_path=path, n_ctx=N_CTX, n_threads=N_THREADS, n_gpu_layers=N_GPU_LAYERS, verbose=True)
    start_time = time.time()
    print("Server startup complete")


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    if llm is None:
        raise HTTPException(503, "Model is loading")

    messages = [{"role": "system", "content": req.system}, {"role": "user", "content": req.prompt}]
    entry = begin_request(req.prompt, kind="generate")

    try:
        max_tokens = _clamp_max_tokens(messages, req.max_tokens)
        t0 = time.time()
        result = llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
        )
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
        result = llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
        )
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
            "model": model_name,
            "usage": usage,
        }
    except HTTPException as e:
        fail_request(entry, e.detail if isinstance(e.detail, str) else str(e.detail))
        raise
    except Exception as e:
        traceback.print_exc()
        fail_request(entry, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"Generation failed: {type(e).__name__}: {e}")


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
    </tr>
  </thead>
  <tbody id="req-tbody">
    <tr><td colspan="5" style="color:#484f58;text-align:center;padding:20px">No requests yet</td></tr>
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

function openModal(idx) {
  const r = recentData[idx];
  if (!r) return;
  document.getElementById('modal-time').textContent = r.time + ' - Request Details';
  document.getElementById('modal-prompt').textContent = r.prompt;
  document.getElementById('modal-response').textContent = r.response;
  document.getElementById('modal-meta').innerHTML =
    `<div class="meta-chip">Prompt Tokens <span>${r.prompt_tokens.toLocaleString()}</span></div>
     <div class="meta-chip">Generated Tokens <span>${r.gen_tokens.toLocaleString()}</span></div>
     <div class="meta-chip">Elapsed <span>${r.elapsed_ms.toLocaleString()} ms</span></div>`;
  document.getElementById('modal-bg').classList.add('show');
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
    const r = await fetch('/stats');
    if (!r.ok) throw new Error();
    const d = await r.json();

    document.getElementById('dot').className = 'dot';
    document.getElementById('status-text').textContent = 'Online';
    document.getElementById('model-name').textContent = d.model || '-';
    document.getElementById('uptime').textContent = fmtUptime(d.uptime_sec);
    document.getElementById('total-req').textContent = d.total_requests.toLocaleString();
    document.getElementById('total-gen').textContent = d.total_generated_tokens.toLocaleString();
    document.getElementById('total-prompt').textContent = d.total_prompt_tokens.toLocaleString();
    document.getElementById('avg-ms').textContent = d.total_requests > 0 ? d.avg_response_ms.toLocaleString() + ' ms' : '-';

    recentData = d.recent || [];
    const tbody = document.getElementById('req-tbody');

    if (recentData.length > 0) {
      tbody.innerHTML = recentData.map((r, i) => {
        const status = r.status || 'done';
        const rowCls = status === 'pending' ? 'clickable pending' : (status === 'error' ? 'clickable error' : 'clickable');
        const badge = status === 'pending'
          ? '<span class="status-badge status-pending">Pending</span>'
          : (status === 'error' ? '<span class="status-badge status-error">Error</span>' : '');
        const elapsed = status === 'pending' ? `${r.elapsed_ms.toLocaleString()} ms elapsed...` : `${r.elapsed_ms.toLocaleString()} ms`;
        const ptCell = status === 'pending' ? '-' : r.prompt_tokens.toLocaleString();
        const gtCell = status === 'pending' ? '-' : r.gen_tokens.toLocaleString();
        const safePrompt = r.prompt.replace(/"/g, '&quot;');

        return `
        <tr class="${rowCls}" onclick="openModal(${i})">
          <td>${r.time.split(' ')[1]}</td>
          <td class="prompt-cell" title="${safePrompt}">${badge}${r.prompt.substring(0,60)}${r.prompt.length > 60 ? '...' : ''}</td>
          <td>${ptCell}</td>
          <td>${gtCell}</td>
          <td>${elapsed}</td>
        </tr>`;
      }).join('');
    } else {
      tbody.innerHTML = '<tr><td colspan="5" style="color:#484f58;text-align:center;padding:20px">No requests yet</td></tr>';
    }

    document.getElementById('last-update').textContent = 'Last update: ' + new Date().toLocaleTimeString();
  } catch (e) {
    document.getElementById('dot').className = 'dot offline';
    document.getElementById('status-text').textContent = 'Offline';
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
