"""Sm_AICoder — Instruction-following 코드 생성 API 서버 (llama-cpp-python + GGUF)"""
import os
import glob
import time
import json
from typing import Optional
from collections import deque
from datetime import datetime

try:
    from llama_cpp import Llama
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, FileResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError as e:
    print(f"설치 필요: pip install llama-cpp-python fastapi uvicorn\n{e}")
    raise

# ── 설정 ──────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR  = os.path.join(BASE_DIR, "models", "gguf")
LOG_DIR    = os.path.join(BASE_DIR, "logs")
LOG_FILE  = os.path.join(LOG_DIR, f"requests_{datetime.now().strftime('%Y%m%d%H%M%S')}.log")
PORT = 8888
N_CTX = 4096
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


def write_log(entry: dict):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def record(prompt_tokens: int, gen_tokens: int, elapsed_ms: float,
           prompt: str, response: str):
    stats["total_requests"] += 1
    stats["total_prompt_tokens"] += prompt_tokens
    stats["total_generated_tokens"] += gen_tokens
    stats["total_elapsed_ms"] += elapsed_ms

    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "prompt": prompt,
        "response": response,
        "prompt_tokens": prompt_tokens,
        "gen_tokens": gen_tokens,
        "elapsed_ms": round(elapsed_ms),
    }
    recent_requests.appendleft(entry)
    write_log(entry)


def find_model() -> str:
    files = glob.glob(os.path.join(MODEL_DIR, "*.gguf"))
    if not files:
        raise FileNotFoundError(
            f"GGUF 모델이 없습니다: {MODEL_DIR}\n"
            "python scripts/download_model.py 로 다운로드하세요."
        )
    return max(files, key=os.path.getsize)


# ── 모델 ──────────────────────────────────────────
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
    print(f"모델 로딩: {model_name}")
    llm = Llama(model_path=path, n_ctx=N_CTX, n_threads=N_THREADS,
                n_gpu_layers=N_GPU_LAYERS, verbose=False)
    start_time = time.time()
    print("서버 준비 완료")


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    if llm is None:
        raise HTTPException(503, "모델 로딩 중")
    messages = [
        {"role": "system", "content": req.system},
        {"role": "user",   "content": req.prompt},
    ]
    t0 = time.time()
    result = llm.create_chat_completion(messages=messages,
        max_tokens=req.max_tokens, temperature=req.temperature, top_p=req.top_p)
    elapsed = (time.time() - t0) * 1000
    choice = result["choices"][0]
    usage = result.get("usage", {})
    pt = usage.get("prompt_tokens", 0)
    gt = usage.get("completion_tokens", 0)
    response_text = choice["message"]["content"]
    record(pt, gt, elapsed, req.prompt, response_text)
    return GenerateResponse(generated=response_text,
        model=model_name, prompt_tokens=pt, generated_tokens=gt)


@app.post("/chat")
def chat(req: ChatRequest):
    if llm is None:
        raise HTTPException(503, "모델 로딩 중")
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    t0 = time.time()
    result = llm.create_chat_completion(messages=messages,
        max_tokens=req.max_tokens, temperature=req.temperature, top_p=req.top_p)
    elapsed = (time.time() - t0) * 1000
    choice = result["choices"][0]
    usage = result.get("usage", {})
    pt = usage.get("prompt_tokens", 0)
    gt = usage.get("completion_tokens", 0)
    response_text = choice["message"]["content"]
    user_msgs = [m.content for m in req.messages if m.role == "user"]
    record(pt, gt, elapsed, user_msgs[-1] if user_msgs else "", response_text)
    return {"response": response_text, "elapsed_ms": round(elapsed),
            "message": choice["message"], "model": model_name, "usage": usage}


@app.get("/health")
def health():
    return {"status": "ok", "model": model_name}


@app.get("/stats")
def get_stats():
    uptime = int(time.time() - start_time) if start_time else 0
    avg_ms = (stats["total_elapsed_ms"] / stats["total_requests"]
              if stats["total_requests"] > 0 else 0)
    items = []
    for r in recent_requests:
        items.append({
            "time": r["time"],
            "prompt": r["prompt"],
            "response": r["response"],
            "prompt_tokens": r["prompt_tokens"],
            "gen_tokens": r["gen_tokens"],
            "elapsed_ms": r["elapsed_ms"],
        })
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
        raise HTTPException(404, "로그 파일 없음")
    return FileResponse(LOG_FILE, filename="requests.log",
                        media_type="text/plain; charset=utf-8")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(DASHBOARD_HTML)


# ── 대시보드 HTML ──────────────────────────────────
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>월평동 이상목 Sm_AICoder Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0d1117; color: #c9d1d9; font-family: 'Segoe UI', sans-serif; padding: 24px; }
  h1 { font-size: 1.4rem; color: #58a6ff; margin-bottom: 4px; }
  .subtitle { font-size: 0.85rem; color: #6e7681; margin-bottom: 24px; }
  .status-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 24px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: #3fb950; box-shadow: 0 0 6px #3fb950; animation: pulse 2s infinite; }
  .dot.offline { background: #f85149; box-shadow: 0 0 6px #f85149; animation: none; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
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
  .prompt-cell { color: #8b949e; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .refresh-info { font-size: 0.75rem; color: #484f58; margin-top: 16px; text-align: right; }
  /* 모달 */
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
<h1>월평동 이상목 Sm_AICoder Dashboard</h1>
<p class="subtitle">Instruction-Following Code Generation Server</p>

<div class="status-bar">
  <div class="dot" id="dot"></div>
  <span class="status-text" id="status-text">연결 확인 중...</span>
</div>

<div class="model-box">
  <div>모델: <span id="model-name">로딩 중...</span> &nbsp;|&nbsp; 업타임: <span id="uptime">-</span></div>
  <a class="btn-log" href="/logs/download" download>로그 다운로드</a>
</div>

<div class="cards">
  <div class="card"><div class="card-label">총 요청 수</div><div class="card-value blue" id="total-req">-</div></div>
  <div class="card"><div class="card-label">생성 토큰 합계</div><div class="card-value green" id="total-gen">-</div></div>
  <div class="card"><div class="card-label">프롬프트 토큰 합계</div><div class="card-value yellow" id="total-prompt">-</div></div>
  <div class="card"><div class="card-label">평균 응답 시간</div><div class="card-value purple" id="avg-ms">-</div></div>
</div>

<div class="section-title">최근 요청 (최대 20건) — 행 클릭 시 상세 보기</div>
<table>
  <thead>
    <tr>
      <th>시각</th>
      <th>프롬프트</th>
      <th>프롬프트 토큰</th>
      <th>생성 토큰</th>
      <th>응답 시간</th>
    </tr>
  </thead>
  <tbody id="req-tbody">
    <tr><td colspan="5" style="color:#484f58;text-align:center;padding:20px">요청 없음</td></tr>
  </tbody>
</table>
<p class="refresh-info">5초마다 자동 갱신 &nbsp;|&nbsp; <span id="last-update">-</span></p>

<!-- 모달 -->
<div class="modal-bg" id="modal-bg" onclick="closeModal(event)">
  <div class="modal">
    <div class="modal-header">
      <h3 id="modal-time">요청 상세</h3>
      <button class="modal-close" onclick="closeModal()">&#x2715;</button>
    </div>
    <div class="modal-body">
      <div class="modal-meta" id="modal-meta"></div>
      <div class="modal-section">
        <label>프롬프트</label>
        <pre id="modal-prompt"></pre>
      </div>
      <div class="modal-section">
        <label>응답</label>
        <pre id="modal-response"></pre>
      </div>
    </div>
  </div>
</div>

<script>
let recentData = [];

function fmtUptime(sec) {
  const h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60), s = sec%60;
  if (h > 0) return h+'h '+m+'m';
  if (m > 0) return m+'m '+s+'s';
  return s+'s';
}

function openModal(idx) {
  const r = recentData[idx];
  if (!r) return;
  document.getElementById('modal-time').textContent = r.time + ' — 요청 상세';
  document.getElementById('modal-prompt').textContent = r.prompt;
  document.getElementById('modal-response').textContent = r.response;
  document.getElementById('modal-meta').innerHTML =
    `<div class="meta-chip">프롬프트 토큰 <span>${r.prompt_tokens.toLocaleString()}</span></div>
     <div class="meta-chip">생성 토큰 <span>${r.gen_tokens.toLocaleString()}</span></div>
     <div class="meta-chip">응답 시간 <span>${r.elapsed_ms.toLocaleString()} ms</span></div>`;
  document.getElementById('modal-bg').classList.add('show');
}

function closeModal(e) {
  if (!e || e.target === document.getElementById('modal-bg') || e.target.classList.contains('modal-close'))
    document.getElementById('modal-bg').classList.remove('show');
}

document.addEventListener('keydown', e => { if (e.key==='Escape') document.getElementById('modal-bg').classList.remove('show'); });

async function refresh() {
  try {
    const r = await fetch('/stats');
    if (!r.ok) throw new Error();
    const d = await r.json();
    document.getElementById('dot').className = 'dot';
    document.getElementById('status-text').textContent = '온라인';
    document.getElementById('model-name').textContent = d.model || '-';
    document.getElementById('uptime').textContent = fmtUptime(d.uptime_sec);
    document.getElementById('total-req').textContent = d.total_requests.toLocaleString();
    document.getElementById('total-gen').textContent = d.total_generated_tokens.toLocaleString();
    document.getElementById('total-prompt').textContent = d.total_prompt_tokens.toLocaleString();
    document.getElementById('avg-ms').textContent = d.total_requests > 0 ? d.avg_response_ms.toLocaleString()+' ms' : '-';

    recentData = d.recent || [];
    const tbody = document.getElementById('req-tbody');
    if (recentData.length > 0) {
      tbody.innerHTML = recentData.map((r, i) => `
        <tr class="clickable" onclick="openModal(${i})">
          <td>${r.time.split(' ')[1]}</td>
          <td class="prompt-cell" title="${r.prompt.replace(/"/g,'&quot;')}">${r.prompt.substring(0,60)}${r.prompt.length>60?'...':''}</td>
          <td>${r.prompt_tokens.toLocaleString()}</td>
          <td>${r.gen_tokens.toLocaleString()}</td>
          <td>${r.elapsed_ms.toLocaleString()} ms</td>
        </tr>`).join('');
    } else {
      tbody.innerHTML = '<tr><td colspan="5" style="color:#484f58;text-align:center;padding:20px">요청 없음</td></tr>';
    }
    document.getElementById('last-update').textContent = '마지막 갱신: ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('dot').className = 'dot offline';
    document.getElementById('status-text').textContent = '오프라인';
  }
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    print(f"Sm_AICoder API 서버 시작: http://localhost:{PORT}")
    print(f"대시보드: http://localhost:{PORT}/")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
