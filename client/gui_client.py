import tkinter as tk
from tkinter import scrolledtext, messagebox
import requests
import threading
import subprocess
import webbrowser
import os
import re
import json
import sys
import time
import ctypes

API_URL = "http://localhost:8888"
APP_ID = "sm.aicoder.client"
ICON_FILE = "icon.ico"
CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CLIENT_DIR)

DARK_BG  = "#0d1117"
PANEL_BG = "#161b22"
BORDER   = "#30363d"
TEXT     = "#c9d1d9"
BLUE     = "#58a6ff"
GREEN    = "#3fb950"
MUTED    = "#6e7681"
INPUT_BG = "#21262d"
RED      = "#f85149"
CODE_FG  = "#79c0ff"
USER_HEADER_BG = "#1f4d2e"
AI_HEADER_BG   = "#0d3818"
CODE_HEADER_BG = "#21262d"
CODE_BLOCK_BG  = "#010409"
HEADER_FG      = "#e6edf3"
INLINE_CODE_BG = "#161b22"
INLINE_CODE_FG = "#ff7b72"

# 에이전트 모드 전용 색상
AGENT_STEP_BG    = "#1c1f26"
AGENT_THOUGHT_FG = "#d29922"
AGENT_TOOL_FG    = "#bc8cff"
AGENT_OK_FG      = "#3fb950"
AGENT_FAIL_FG    = "#f85149"
AGENT_ANSWER_BG  = "#0d2818"

# 레이아웃 설정 파일 (스크립트 옆에 저장)
LAYOUT_FILE = os.path.join(CLIENT_DIR, "gui_layout.json")

# 기본 레이아웃: 응답창 크게(65%), 입력창 작게(35%), 상단 75% / 하단 25%
DEFAULT_LAYOUT = {
    "geometry": "1280x840",
    "v_ratio":  0.75,   # 상하 분할 — 상단 비율
    "h_ratio":  0.35,   # 좌우 분할 — 입력(좌) 비율
}


def get_resource_path(filename: str) -> str:
    """Return a path that works for both source runs and PyInstaller onefile."""
    base_dir = getattr(sys, "_MEIPASS", CLIENT_DIR)
    return os.path.join(base_dir, filename)


def configure_windows_app_id():
    if os.name != "nt":
        return

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def apply_window_icon(root: tk.Tk):
    icon_path = get_resource_path(ICON_FILE)
    if not os.path.exists(icon_path):
        return

    try:
        root.iconbitmap(default=icon_path)
    except Exception:
        pass


class StarCoderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("월평동이상목 Sm_AICoder")
        self.root.configure(bg=DARK_BG)
        self.root.minsize(900, 640)
        apply_window_icon(self.root)

        self.history     = []
        self.temperature = tk.DoubleVar(value=0.2)
        self.max_tokens  = tk.IntVar(value=1024)
        self._sending    = False
        self._layout     = self._load_layout()

        # 에이전트 모드
        self._agent_mode = False
        self._agent_available = False
        self._agent_session_id = "gui-default"

        # 저장된(또는 기본) 창 크기 적용
        self.root.geometry(self._layout["geometry"])

        self._build_toolbar()
        self._build_main()
        self._check_server()

        # 창 크기/위치 변경 시 저장
        self.root.bind("<Configure>", self._on_configure)

    # ──────────────────────────────────────────
    # 레이아웃 저장 / 불러오기
    # ──────────────────────────────────────────
    def _load_layout(self) -> dict:
        try:
            with open(LAYOUT_FILE, encoding="utf-8") as f:
                data = json.load(f)
            # 필수 키 없으면 기본값으로 보완
            for k, v in DEFAULT_LAYOUT.items():
                data.setdefault(k, v)
            return data
        except Exception:
            return dict(DEFAULT_LAYOUT)

    def _save_layout(self):
        try:
            self._layout["geometry"] = self.root.winfo_geometry()
            with open(LAYOUT_FILE, "w", encoding="utf-8") as f:
                json.dump(self._layout, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_configure(self, event):
        # 루트 창 이벤트만 처리 (자식 위젯 Configure 무시)
        if event.widget is self.root:
            self._save_layout()

    # sash 드래그 끝났을 때 비율 저장
    def _on_v_sash(self, event):
        try:
            total = self._outer.winfo_height()
            if total > 10:
                pos = self._outer.sash_coord(0)[1]
                self._layout["v_ratio"] = pos / total
                self._save_layout()
        except Exception:
            pass

    def _on_h_sash(self, event):
        try:
            total = self._top_pane.winfo_width()
            if total > 10:
                pos = self._top_pane.sash_coord(0)[0]
                self._layout["h_ratio"] = pos / total
                self._save_layout()
        except Exception:
            pass

    # 창 렌더 완료 후 sash 위치 적용
    def _apply_sash(self):
        self.root.update_idletasks()

        v_total = self._outer.winfo_height()
        if v_total > 10:
            self._outer.sash_place(0, 0, int(v_total * self._layout["v_ratio"]))

        h_total = self._top_pane.winfo_width()
        if h_total > 10:
            self._top_pane.sash_place(0, int(h_total * self._layout["h_ratio"]), 0)

    # ──────────────────────────────────────────
    # Toolbar
    # ──────────────────────────────────────────
    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg=PANEL_BG, pady=7, padx=14,
                       relief=tk.FLAT, bd=0)
        bar.pack(fill=tk.X)

        # 왼쪽: 상태
        self.dot = tk.Label(bar, text="●", fg=GREEN, bg=PANEL_BG,
                            font=("Segoe UI", 13))
        self.dot.pack(side=tk.LEFT, padx=(0, 5))

        self.status_lbl = tk.Label(bar, text="서버 확인 중...",
                                   fg=MUTED, bg=PANEL_BG,
                                   font=("Segoe UI", 9))
        self.status_lbl.pack(side=tk.LEFT, padx=(0, 12))

        # 서버 제어 버튼
        tk.Button(bar, text="▶ 서버 시작", command=self._server_start,
                  bg="#1f4d2e", fg=GREEN, relief=tk.FLAT,
                  font=("Segoe UI", 9), padx=10, pady=3,
                  cursor="hand2").pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(bar, text="■ 서버 정지", command=self._server_stop,
                  bg="#4d1f1f", fg=RED, relief=tk.FLAT,
                  font=("Segoe UI", 9), padx=10, pady=3,
                  cursor="hand2").pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(bar, text="⬡ 대시보드", command=self._open_dashboard,
                  bg=INPUT_BG, fg=BLUE, relief=tk.FLAT,
                  font=("Segoe UI", 9), padx=10, pady=3,
                  cursor="hand2").pack(side=tk.LEFT, padx=(0, 4))

        # 모드 전환 버튼 (채팅 ↔ 에이전트)
        self.mode_btn = tk.Button(
            bar, text="채팅 모드", command=self._toggle_mode,
            bg="#1a1e2e", fg="#bc8cff", relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"), padx=12, pady=3,
            cursor="hand2",
        )
        self.mode_btn.pack(side=tk.LEFT, padx=(8, 4))

        self.mode_indicator = tk.Label(
            bar, text="", fg=MUTED, bg=PANEL_BG,
            font=("Segoe UI", 8),
        )
        self.mode_indicator.pack(side=tk.LEFT, padx=(0, 4))

        # 오른쪽: 파라미터 + 초기화
        tk.Button(bar, text="대화 초기화", command=self._clear_history,
                  bg=INPUT_BG, fg=MUTED, relief=tk.FLAT,
                  font=("Segoe UI", 9), padx=10, pady=3,
                  cursor="hand2").pack(side=tk.RIGHT, padx=4)

        tk.Label(bar, text="최대 토큰:", fg=MUTED, bg=PANEL_BG,
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=(16, 0))
        tk.Spinbox(bar, from_=64, to=4096, increment=64,
                   textvariable=self.max_tokens, width=6,
                   bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                   relief=tk.FLAT, font=("Segoe UI", 9),
                   buttonbackground=BORDER).pack(side=tk.RIGHT, padx=(4, 0))

        tk.Label(bar, text="온도:", fg=MUTED, bg=PANEL_BG,
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=(16, 0))
        tk.Spinbox(bar, from_=0.0, to=2.0, increment=0.1,
                   textvariable=self.temperature, width=5,
                   bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                   relief=tk.FLAT, font=("Segoe UI", 9), format="%.1f",
                   buttonbackground=BORDER).pack(side=tk.RIGHT, padx=(4, 0))

    # ──────────────────────────────────────────
    # Main 3-panel layout
    # ──────────────────────────────────────────
    def _build_main(self):
        self._outer = tk.PanedWindow(self.root, orient=tk.VERTICAL,
                                     bg=BORDER, sashwidth=5,
                                     sashrelief=tk.FLAT, bd=0)
        self._outer.pack(fill=tk.BOTH, expand=True)
        self._outer.bind("<ButtonRelease-1>", self._on_v_sash)

        self._top_pane = tk.PanedWindow(self._outer, orient=tk.HORIZONTAL,
                                        bg=BORDER, sashwidth=5,
                                        sashrelief=tk.FLAT, bd=0)
        self._outer.add(self._top_pane, minsize=200)
        self._top_pane.bind("<ButtonRelease-1>", self._on_h_sash)

        self._build_input_panel(self._top_pane)
        self._build_copy_panel(self._top_pane)

        self._build_result_panel(self._outer)

        # 렌더 완료 후 sash 비율 적용
        self.root.after(200, self._apply_sash)

    # ── Panel 1: 명령 입력 ──────────────────
    def _build_input_panel(self, parent):
        frame = tk.Frame(parent, bg=PANEL_BG)
        parent.add(frame, minsize=200)

        self._section_label(frame, "① 명령 입력")

        # btn_row를 먼저 BOTTOM에 pack해야 expand=True인 input_box에 밀리지 않음
        btn_row = tk.Frame(frame, bg=PANEL_BG, pady=6, padx=8)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X)

        self.send_btn = tk.Button(
            btn_row, text="전송  (Ctrl+Enter)", command=self._send,
            bg=BLUE, fg=DARK_BG, relief=tk.FLAT,
            font=("Segoe UI", 10, "bold"), padx=14, pady=6,
            cursor="hand2",
        )
        self.send_btn.pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            btn_row, text="입력 지우기",
            command=lambda: self.input_box.delete("1.0", tk.END),
            bg=INPUT_BG, fg=MUTED, relief=tk.FLAT,
            font=("Segoe UI", 9), padx=10, pady=6, cursor="hand2",
        ).pack(side=tk.LEFT)

        self.turn_lbl = tk.Label(btn_row, text="대화: 0턴",
                                 fg=MUTED, bg=PANEL_BG,
                                 font=("Segoe UI", 9))
        self.turn_lbl.pack(side=tk.RIGHT)

        self.input_box = tk.Text(
            frame, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
            relief=tk.FLAT, font=("Consolas", 11), wrap=tk.WORD,
            padx=10, pady=10, undo=True,
        )
        self.input_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
        self.input_box.bind("<Control-Return>", lambda e: self._send())

    # ── Panel 2: 응답 ─────────────────────
    def _build_copy_panel(self, parent):
        frame = tk.Frame(parent, bg=PANEL_BG)
        parent.add(frame, minsize=300)

        hdr = tk.Frame(frame, bg=PANEL_BG)
        hdr.pack(fill=tk.X, padx=8)

        self._section_label(hdr, "② 응답", side=tk.LEFT)

        self.copy_btn = tk.Button(
            hdr, text="클립보드 복사", command=self._copy_code,
            bg=INPUT_BG, fg=GREEN, relief=tk.FLAT,
            font=("Segoe UI", 9), padx=10, pady=3, cursor="hand2",
        )
        self.copy_btn.pack(side=tk.RIGHT, pady=6)

        self.copy_hint = tk.Label(
            frame,
            text="코드 블록(``` ```)이 자동 추출됩니다.  없으면 전체 응답이 표시됩니다.",
            fg=MUTED, bg=PANEL_BG, font=("Segoe UI", 8),
        )
        self.copy_hint.pack(anchor=tk.W, padx=10, pady=(0, 4))

        self.copy_box = tk.Text(
            frame, bg=DARK_BG, fg=CODE_FG, insertbackground=CODE_FG,
            relief=tk.FLAT, font=("Consolas", 11), wrap=tk.WORD,
            padx=10, pady=10, state=tk.DISABLED,
        )
        self.copy_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    # ── Panel 3: 실행 결과 ────────────────
    def _build_result_panel(self, parent):
        frame = tk.Frame(parent, bg=PANEL_BG)
        parent.add(frame, minsize=100)

        hdr = tk.Frame(frame, bg=PANEL_BG)
        hdr.pack(fill=tk.X, padx=8)

        self._section_label(hdr, "③ 실행 결과 (전체 AI 응답)", side=tk.LEFT)

        self.elapsed_lbl = tk.Label(hdr, text="", fg=MUTED, bg=PANEL_BG,
                                    font=("Segoe UI", 9))
        self.elapsed_lbl.pack(side=tk.RIGHT, pady=6)

        self.result_box = scrolledtext.ScrolledText(
            frame, bg=DARK_BG, fg=TEXT, insertbackground=TEXT,
            relief=tk.FLAT, font=("Consolas", 11), wrap=tk.WORD,
            padx=10, pady=10, state=tk.DISABLED,
        )
        self.result_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # 태그 정의 (마크다운 스타일링)
        self.result_box.tag_config("user_header",    background=USER_HEADER_BG, foreground=GREEN,        font=("Segoe UI", 10, "bold"))
        self.result_box.tag_config("ai_header",      background=AI_HEADER_BG,   foreground=GREEN,        font=("Segoe UI", 10, "bold"))
        self.result_box.tag_config("divider",        foreground=BORDER)
        self.result_box.tag_config("code_header",    background=CODE_HEADER_BG,  foreground=MUTED,        font=("Consolas", 9))
        self.result_box.tag_config("code_block",     background=CODE_BLOCK_BG,   foreground=CODE_FG,      font=("Consolas", 10))
        self.result_box.tag_config("header",         foreground=HEADER_FG,       font=("Consolas", 12, "bold"))
        self.result_box.tag_config("bold",           foreground=HEADER_FG,       font=("Consolas", 11, "bold"))
        self.result_box.tag_config("inline_code",    background=INLINE_CODE_BG,  foreground=INLINE_CODE_FG, font=("Consolas", 10))
        self.result_box.tag_config("normal",         foreground=TEXT,            font=("Consolas", 11))

        # 에이전트 모드 전용 태그
        self.result_box.tag_config("agent_step",     background=AGENT_STEP_BG,   foreground=MUTED,           font=("Segoe UI", 9))
        self.result_box.tag_config("agent_thought",  foreground=AGENT_THOUGHT_FG, font=("Segoe UI", 10))
        self.result_box.tag_config("agent_tool",     foreground=AGENT_TOOL_FG,    font=("Consolas", 10, "bold"))
        self.result_box.tag_config("agent_ok",       foreground=AGENT_OK_FG,      font=("Consolas", 9))
        self.result_box.tag_config("agent_fail",     foreground=AGENT_FAIL_FG,    font=("Consolas", 9))
        self.result_box.tag_config("agent_answer",   background=AGENT_ANSWER_BG,  foreground=GREEN,           font=("Consolas", 11))

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────
    def _section_label(self, parent, text, side=None):
        lbl = tk.Label(parent, text=text, fg=BLUE, bg=PANEL_BG,
                       font=("Segoe UI", 10, "bold"), pady=8)
        if side:
            lbl.pack(side=side)
        else:
            lbl.pack(anchor=tk.W, padx=8)
        return lbl

    def _set_text(self, widget, text):
        widget.config(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.config(state=tk.DISABLED)

    def _extract_code(self, text):
        blocks = re.findall(r"```(?:\w*)\n?(.*?)```", text, re.DOTALL)
        if blocks:
            return "\n\n".join(b.strip() for b in blocks)
        return text.strip()

    def _append_message(self, role, content):
        """마크다운 스타일로 메시지 추가"""
        self.result_box.config(state=tk.NORMAL)

        # 헤더 추가
        if len(self.result_box.get("1.0", tk.END).strip()) > 0:
            self.result_box.insert(tk.END, "\n")

        if role == "user":
            self.result_box.insert(tk.END, "You ▶ ", "user_header")
        else:
            self.result_box.insert(tk.END, "Sm_AICoder ▶ ", "ai_header")

        # 콘텐츠 파싱 및 삽입
        self._parse_and_insert(content)

        # 구분선 추가
        self.result_box.insert(tk.END, "\n" + "─" * 60 + "\n", "divider")
        self.result_box.config(state=tk.DISABLED)
        self.result_box.see(tk.END)

    def _parse_and_insert(self, text):
        """마크다운 텍스트 파싱 및 스타일과 함께 삽입"""
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            # 코드블록 처리
            if line.strip().startswith("```"):
                lang = line.strip()[3:].strip()
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # 닫는 ``` 건너뛰기

                # 코드블록 헤더 (언어 표시)
                if lang:
                    self.result_box.insert(tk.END, f" {lang} \n", "code_header")
                self.result_box.insert(tk.END, "\n".join(code_lines) + "\n\n", "code_block")
                continue

            # 헤더 (## ###) 처리
            if line.strip().startswith("##"):
                level = len(line) - len(line.lstrip("#"))
                header_text = line.lstrip("#").strip()
                self.result_box.insert(tk.END, header_text + "\n", "header")
                i += 1
                continue

            # 일반 텍스트 (마크다운 인라인 요소 파싱)
            if line.strip():
                self._parse_inline(line)
                self.result_box.insert(tk.END, "\n")
            else:
                self.result_box.insert(tk.END, "\n")
            i += 1

    def _parse_inline(self, text):
        """인라인 마크다운 요소 파싱 (**bold**, `code`)"""
        # 정규식으로 패턴 찾기
        pattern = r"(\*\*[^*]+\*\*|`[^`]+`|[^*`]+)"
        matches = re.findall(pattern, text)

        for match in matches:
            if match.startswith("**") and match.endswith("**"):
                # 볼드
                self.result_box.insert(tk.END, match[2:-2], "bold")
            elif match.startswith("`") and match.endswith("`"):
                # 인라인 코드
                self.result_box.insert(tk.END, match[1:-1], "inline_code")
            else:
                # 일반 텍스트
                self.result_box.insert(tk.END, match, "normal")

    # ──────────────────────────────────────────
    # Actions
    # ──────────────────────────────────────────
    def _send(self):
        if self._sending:
            return
        prompt = self.input_box.get("1.0", tk.END).strip()
        if not prompt:
            return

        self._sending = True
        self.send_btn.config(state=tk.DISABLED, text="생성 중...")
        self._set_text(self.copy_box, "")
        self.elapsed_lbl.config(text="")

        # 생성 중 표시
        self.result_box.config(state=tk.NORMAL)
        if len(self.result_box.get("1.0", tk.END).strip()) > 0:
            self.result_box.insert(tk.END, "\n")

        if self._agent_mode:
            self.result_box.insert(tk.END, "⏳ 에이전트 실행 중...\n", "agent_thought")
        else:
            self.result_box.insert(tk.END, "⏳ 생성 중입니다...\n", "normal")
        self.result_box.config(state=tk.DISABLED)
        self.result_box.see(tk.END)

        if self._agent_mode:
            threading.Thread(target=self._run_agent, args=(prompt,), daemon=True).start()
        else:
            threading.Thread(target=self._run_chat, args=(prompt,), daemon=True).start()

    def _run_chat(self, prompt: str):
        """채팅 모드 — 기존 /chat 엔드포인트 호출"""
        try:
            payload = {
                "messages": self.history + [{"role": "user", "content": prompt}],
                "temperature": self.temperature.get(),
                "max_tokens": self.max_tokens.get(),
            }
            r = requests.post(f"{API_URL}/chat", json=payload, timeout=180)
            r.raise_for_status()
            data = r.json()
            response = data.get("response", "")
            elapsed  = data.get("elapsed_ms", 0)

            self.history.append({"role": "user",      "content": prompt})
            self.history.append({"role": "assistant", "content": response})

            code = self._extract_code(response)
            self.root.after(0, lambda: self._on_response(response, code, elapsed))
        except Exception as e:
            self.root.after(0, lambda: self._on_error(str(e)))
        finally:
            self.root.after(0, self._done_sending)

    def _run_agent(self, prompt: str):
        """에이전트 모드 — /agent/stream 엔드포인트 스트리밍 수신"""
        try:
            payload = {
                "message": prompt,
                "session_id": self._agent_session_id,
                "working_dir": PROJECT_ROOT,
                "max_iterations": 15,
                "temperature": self.temperature.get(),
                "max_tokens": self.max_tokens.get(),
            }

            # 시작 시: ③ 창에 사용자 입력 + 실행 과정 헤더 먼저 그린다
            self.root.after(0, lambda: self._agent_stream_begin(prompt))

            with requests.post(
                f"{API_URL}/agent/stream",
                json=payload,
                stream=True,
                timeout=(10, 600),
            ) as r:
                r.raise_for_status()
                last_beat = time.time()
                for raw in r.iter_lines(decode_unicode=True):
                    if raw is None:
                        continue
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    t = evt.get("type")
                    if t == "step":
                        step = evt.get("step", {})
                        self.root.after(0, lambda s=step: self._agent_stream_step(s))
                    elif t == "heartbeat":
                        last_beat = time.time()
                        self.root.after(0, lambda: self._agent_stream_heartbeat())
                    elif t == "final":
                        answer = evt.get("answer", "")
                        elapsed = evt.get("elapsed_ms", 0)
                        self.root.after(0, lambda a=answer, e=elapsed: self._agent_stream_final(a, e))
                    elif t == "error":
                        err = evt.get("error", "알 수 없는 오류")
                        self.root.after(0, lambda m=err: self._on_error(m))

        except Exception as e:
            self.root.after(0, lambda: self._on_error(str(e)))
        finally:
            self.root.after(0, self._done_sending)

    def _on_response(self, response, code, elapsed_ms):
        # 사용자 질문 추가
        if len(self.history) >= 2:
            user_msg = self.history[-2]["content"]
            self._append_message("user", user_msg)

        # AI 응답 추가
        self._append_message("assistant", response)

        self._set_text(self.copy_box, code)
        self.elapsed_lbl.config(text=f"{elapsed_ms / 1000:.1f}초")
        turns = len(self.history) // 2
        self.turn_lbl.config(text=f"대화: {turns}턴")

    def _agent_stream_begin(self, prompt: str):
        """스트리밍 시작 — '에이전트 실행 중' 플레이스홀더 제거하고 헤더 렌더"""
        self.result_box.config(state=tk.NORMAL)

        # '⏳ 에이전트 실행 중...' 한 줄 제거
        content = self.result_box.get("1.0", tk.END)
        marker = "⏳ 에이전트 실행 중...\n"
        idx = content.rfind(marker)
        if idx >= 0:
            start = f"1.0+{idx}c"
            end = f"1.0+{idx + len(marker)}c"
            self.result_box.delete(start, end)

        self.result_box.insert(tk.END, "You ▶ ", "user_header")
        self.result_box.insert(tk.END, prompt + "\n", "normal")
        self.result_box.insert(tk.END, "\n", "normal")
        self.result_box.insert(tk.END, "Agent ▶ 실행 과정\n", "ai_header")
        self.result_box.config(state=tk.DISABLED)
        self.result_box.see(tk.END)

        self._agent_step_count = 0
        self._agent_last_beat = time.time()
        self.elapsed_lbl.config(text="⏳ 실행 중...")

    def _agent_stream_step(self, step: dict):
        """스트리밍 단계 이벤트 — 즉시 ③ 창에 추가"""
        self.result_box.config(state=tk.NORMAL)
        self._render_agent_step(step)
        self.result_box.config(state=tk.DISABLED)
        self.result_box.see(tk.END)

        self._agent_step_count = getattr(self, "_agent_step_count", 0) + 1
        self._agent_last_beat = time.time()

    def _agent_stream_heartbeat(self):
        """2초마다 서버가 살아있음을 알림 — 상단 경과 표시 갱신"""
        self._agent_last_beat = time.time()
        n = getattr(self, "_agent_step_count", 0)
        self.elapsed_lbl.config(text=f"⏳ 실행 중... ({n}단계)")

    def _agent_stream_final(self, answer: str, elapsed_ms: int):
        """최종 답변 이벤트"""
        self.result_box.config(state=tk.NORMAL)
        self.result_box.insert(tk.END, "\n", "normal")
        self.result_box.insert(tk.END, " 최종 답변 \n", "ai_header")
        self._parse_and_insert(answer)
        self.result_box.insert(tk.END, "\n" + "─" * 60 + "\n", "divider")
        self.result_box.config(state=tk.DISABLED)
        self.result_box.see(tk.END)

        code = self._extract_code(answer)
        self._set_text(self.copy_box, code)
        n = getattr(self, "_agent_step_count", 0)
        self.elapsed_lbl.config(text=f"{elapsed_ms / 1000:.1f}초 ({n}단계)")

    def _render_agent_step(self, step: dict):
        """에이전트 단계 하나를 결과 패널에 렌더링"""
        step_type = step.get("type", "")

        if step_type == "thinking":
            i = step.get("iteration", "?")
            self.result_box.insert(tk.END, f"  [{i}] ", "agent_step")
            self.result_box.insert(tk.END, "생각 중...\n", "agent_step")

        elif step_type == "action":
            i = step.get("iteration", "?")
            thought = step.get("thought", "")
            action = step.get("action", "")
            args = step.get("arguments", {})

            self.result_box.insert(tk.END, f"  [{i}] ", "agent_step")
            self.result_box.insert(tk.END, f"{thought}\n", "agent_thought")

            if action != "answer":
                args_str = json.dumps(args, ensure_ascii=False)
                if len(args_str) > 100:
                    args_str = args_str[:100] + "..."
                self.result_box.insert(tk.END, f"      ", "agent_step")
                self.result_box.insert(tk.END, f"{action}", "agent_tool")
                self.result_box.insert(tk.END, f"({args_str})\n", "agent_step")

        elif step_type == "tool_result":
            ok = step.get("ok", False)
            result = step.get("result", "")
            tag = "agent_ok" if ok else "agent_fail"
            status = "OK" if ok else "FAIL"
            # 결과가 길면 잘라냄
            if len(result) > 150:
                result = result[:150] + "..."
            self.result_box.insert(tk.END, f"      [{status}] ", tag)
            self.result_box.insert(tk.END, f"{result}\n", "agent_step")

        elif step_type == "parse_error":
            self.result_box.insert(tk.END, "      ", "agent_step")
            self.result_box.insert(tk.END, "JSON 파싱 실패 — 재시도\n", "agent_fail")

    def _on_error(self, msg):
        self.result_box.config(state=tk.NORMAL)
        # 이전 "생성 중..." 제거
        content = self.result_box.get("1.0", tk.END)
        if content.endswith("⏳ 생성 중입니다...\n"):
            self.result_box.delete("1.0" if not content[:-21].strip() else "end-21c", tk.END)

        self.result_box.insert(tk.END, f"❌ 오류: {msg}\n", "normal")
        self.result_box.config(state=tk.DISABLED)
        self._set_text(self.copy_box, "")

    def _done_sending(self):
        self._sending = False
        self.send_btn.config(state=tk.NORMAL, text="전송  (Ctrl+Enter)")

    def _copy_code(self):
        text = self.copy_box.get("1.0", tk.END).strip()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.copy_btn.config(text="복사됨 ✓")
        self.root.after(2000, lambda: self.copy_btn.config(text="클립보드 복사"))

    def _toggle_mode(self):
        """채팅 모드 ↔ 에이전트 모드 전환"""
        if not self._agent_available:
            messagebox.showwarning(
                "에이전트 비활성",
                "에이전트 하네스가 서버에 로드되지 않았습니다.\n"
                "서버를 재시작해 주세요.",
            )
            return

        self._agent_mode = not self._agent_mode
        if self._agent_mode:
            self.mode_btn.config(text="에이전트 모드", bg="#2d1a4e", fg="#bc8cff")
            self.mode_indicator.config(text="파일탐색·패치·테스트 자동실행", fg="#bc8cff")
            self.send_btn.config(bg="#bc8cff", fg=DARK_BG)
        else:
            self.mode_btn.config(text="채팅 모드", bg="#1a1e2e", fg="#bc8cff")
            self.mode_indicator.config(text="")
            self.send_btn.config(bg=BLUE, fg=DARK_BG)

    def _clear_history(self):
        self.history = []
        self.result_box.config(state=tk.NORMAL)
        self.result_box.delete("1.0", tk.END)
        self.result_box.config(state=tk.DISABLED)
        self._set_text(self.copy_box, "")
        self.elapsed_lbl.config(text="")
        self.turn_lbl.config(text="대화: 0턴")

        # 에이전트 세션도 초기화
        if self._agent_mode:
            def reset():
                try:
                    requests.post(
                        f"{API_URL}/agent/reset",
                        params={"session_id": self._agent_session_id},
                        timeout=5,
                    )
                except Exception:
                    pass
            threading.Thread(target=reset, daemon=True).start()

    def _run_ps1(self, script_name):
        script = os.path.join(PROJECT_ROOT, script_name)
        subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", script],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

    def _server_start(self):
        self._run_ps1("start_server.ps1")

    def _server_stop(self):
        self._run_ps1("stop_server.ps1")

    def _open_dashboard(self):
        webbrowser.open(API_URL)

    # ──────────────────────────────────────────
    # Server health check (5초마다)
    # ──────────────────────────────────────────
    def _check_server(self):
        def check():
            try:
                r = requests.get(f"{API_URL}/health", timeout=3)
                data = r.json()
                model = data.get("model", "unknown")

                # 에이전트 가용 여부 확인
                agent_ok = False
                try:
                    ra = requests.get(f"{API_URL}/agent/sessions", timeout=3)
                    agent_ok = ra.status_code == 200
                except Exception:
                    pass

                self.root.after(0, lambda: self._set_online(True, model, agent_ok))
            except Exception:
                self.root.after(0, lambda: self._set_online(False, "", False))
            self.root.after(5000, self._check_server)

        threading.Thread(target=check, daemon=True).start()

    def _set_online(self, online, model, agent_ok=False):
        self._agent_available = agent_ok
        if online:
            self.dot.config(fg=GREEN)
            agent_tag = " + Agent" if agent_ok else ""
            self.status_lbl.config(fg=MUTED, text=f"온라인  │  {model}{agent_tag}")
        else:
            self.dot.config(fg=RED)
            self.status_lbl.config(fg=RED, text="서버 오프라인 — localhost:8888")
            self._agent_available = False


if __name__ == "__main__":
    configure_windows_app_id()
    root = tk.Tk()
    StarCoderGUI(root)
    root.mainloop()
