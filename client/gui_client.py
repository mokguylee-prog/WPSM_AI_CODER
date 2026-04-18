import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, simpledialog, ttk
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
from pathlib import Path

try:
    from PIL import ImageGrab, Image, ImageTk
except Exception:
    ImageGrab = None
    Image = None
    ImageTk = None

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
STATE_FILE = os.path.join(CLIENT_DIR, "app_state.json")

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


class ToolTip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _event=None):
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.geometry(f"+{x}+{y}")
        label = tk.Label(self.tip, text=self.text, bg="#111827", fg="#e5e7eb",
                         relief=tk.SOLID, bd=1, padx=8, pady=4,
                         font=("Segoe UI", 8))
        label.pack()

    def hide(self, _event=None):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


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
        # P4-3: in-flight 가드. 단일 세션 가정; 멀티세션 확장 시 dict[session_id, bool] 로 변경.
        self._inflight: bool = False
        self._layout     = self._load_layout()
        self._state      = self._load_state()
        self._open_folder = self._layout.get("open_folder", PROJECT_ROOT)
        self._attachments = []
        self._folder_rows = []
        self._tree_nodes = {}
        self._preview_image = None
        self._pending_approval_command = ""
        self._pending_approval_timeout = 30
        self._approval_dialog = None
        self._always_approve = bool(self._layout.get("always_approve", False))
        self._cancel_requested = False
        self._draft_save_job = None
        self._busy_mode = ""
        self._active_stream_response = None
        self._chat_text_buffer = []
        self._agent_step_buffer = []
        self._buffer_flush_job = None
        self._context_injected = False   # P2-1: 첫 턴 1회만 컨텍스트 주입 플래그

        # 에이전트 모드
        self._agent_mode = bool(self._state.get("agent_mode", False))
        self._agent_available = False
        self._agent_session_id = "gui-default"

        # 저장된(또는 기본) 창 크기 적용
        self.root.geometry(self._layout["geometry"])

        self._build_toolbar()
        self._build_main()
        self._restore_state()
        self._check_server()

        # 창 크기/위치 변경 시 저장
        self.root.bind("<Configure>", self._on_configure)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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
            data.setdefault("open_folder", PROJECT_ROOT)
            data.setdefault("always_approve", False)
            return data
        except Exception:
            data = dict(DEFAULT_LAYOUT)
            data["open_folder"] = PROJECT_ROOT
            data["always_approve"] = False
            return data

    def _load_state(self) -> dict:
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("history", [])
            data.setdefault("result_text", "")
            data.setdefault("copy_text", "")
            data.setdefault("draft_command", "")
            data.setdefault("agent_mode", False)
            return data
        except Exception:
            return {
                "history": [],
                "result_text": "",
                "copy_text": "",
                "draft_command": "",
                "agent_mode": False,
            }

    def _save_layout(self):
        try:
            self._layout["geometry"] = self.root.winfo_geometry()
            self._layout["open_folder"] = self._open_folder or PROJECT_ROOT
            self._layout["always_approve"] = self._always_approve
            with open(LAYOUT_FILE, "w", encoding="utf-8") as f:
                json.dump(self._layout, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _save_state(self):
        try:
            if hasattr(self, "input_box"):
                self._state["draft_command"] = self.input_box.get("1.0", tk.END).rstrip("\n")
            if hasattr(self, "result_box"):
                self._state["result_text"] = self.result_box.get("1.0", tk.END).rstrip("\n")
            if hasattr(self, "copy_box"):
                self._state["copy_text"] = self.copy_box.get("1.0", tk.END).rstrip("\n")
            self._state["history"] = self.history
            self._state["agent_mode"] = self._agent_mode
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
            if hasattr(self, "folder_tree"):
                self._refresh_folder_view(select_path=self._open_folder)
        except Exception:
            pass

    def _restore_state(self):
        draft = self._state.get("draft_command", "")
        if draft and hasattr(self, "input_box"):
            self.input_box.delete("1.0", tk.END)
            self.input_box.insert("1.0", draft)
        if hasattr(self, "result_box"):
            result_text = self._state.get("result_text", "")
            if result_text:
                self._set_text(self.result_box, result_text)
        if hasattr(self, "copy_box"):
            copy_text = self._state.get("copy_text", "")
            if copy_text:
                self._set_text(self.copy_box, copy_text)
        self.history = list(self._state.get("history", []))
        self._apply_mode_ui()

    def _schedule_layout_save(self):
        if self._draft_save_job is not None:
            try:
                self.root.after_cancel(self._draft_save_job)
            except Exception:
                pass
        self._draft_save_job = self.root.after(300, self._save_state)

    def _on_input_changed(self, event=None):
        self._schedule_layout_save()

    def _on_close(self):
        self._save_layout()
        self._refresh_folder_view(select_path=self._open_folder)
        self._save_state()
        self.root.destroy()

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
        self.status_bar = tk.Label(
            bar, text="대기 중", fg=TEXT, bg="#1f2937", font=("Segoe UI", 10, "bold"),
            padx=10, pady=3
        )
        self.status_bar.pack(side=tk.LEFT, padx=(12, 0))

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

        self._build_folder_panel(self._top_pane)
        self._build_editor_panel(self._top_pane)
        self._build_copy_panel(self._top_pane)

        self._build_result_panel(self._outer)
        self._build_command_panel(self._outer)

        # 렌더 완료 후 sash 비율 적용
        self.root.after(200, self._apply_sash)

    # ── Panel 1: 명령 입력 ──────────────────
    def _build_folder_panel(self, parent):
        frame = tk.Frame(parent, bg=PANEL_BG)
        parent.add(frame, minsize=240)

        hdr = tk.Frame(frame, bg=PANEL_BG)
        hdr.pack(fill=tk.X, padx=8)
        self._section_label(hdr, "OpenFolder", side=tk.LEFT)

        tk.Button(
            hdr, text="Open Folder", command=self._open_folder_dialog,
            bg=INPUT_BG, fg=BLUE, relief=tk.FLAT,
            font=("Segoe UI", 9), padx=10, pady=3, cursor="hand2",
        ).pack(side=tk.RIGHT, pady=6)

        btn_row = tk.Frame(frame, bg=PANEL_BG)
        btn_row.pack(fill=tk.X, padx=8, pady=(2, 6))

        tk.Button(
            btn_row, text="New File", command=self._create_file,
            bg=INPUT_BG, fg=GREEN, relief=tk.FLAT,
            font=("Segoe UI", 9), padx=10, pady=3, cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            btn_row, text="New Folder", command=self._create_folder,
            bg=INPUT_BG, fg=GREEN, relief=tk.FLAT,
            font=("Segoe UI", 9), padx=10, pady=3, cursor="hand2",
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_row, text="Delete", command=self._delete_selected_item,
            bg="#4d1f1f", fg=RED, relief=tk.FLAT,
            font=("Segoe UI", 9), padx=10, pady=3, cursor="hand2",
        ).pack(side=tk.RIGHT)

        self.folder_path_lbl = tk.Label(
            frame, text=self._open_folder, fg=MUTED, bg=PANEL_BG,
            font=("Segoe UI", 8), wraplength=220, justify=tk.LEFT,
        )
        self.folder_path_lbl.pack(anchor=tk.W, padx=10, pady=(0, 4))

        tree_frame = tk.Frame(frame, bg=PANEL_BG)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        self.folder_tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.folder_tree.yview)
        self.folder_tree.configure(yscrollcommand=tree_scroll.set)
        self.folder_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.folder_tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.folder_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        preview = tk.Frame(frame, bg=PANEL_BG)
        preview.pack(fill=tk.X, padx=8, pady=(0, 8))
        tk.Label(preview, text="Preview", fg=BLUE, bg=PANEL_BG, font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)
        self.preview_image_lbl = tk.Label(preview, bg=DARK_BG, width=32, height=10)
        self.preview_image_lbl.pack(fill=tk.X, pady=(4, 4))
        self.preview_text_lbl = tk.Label(preview, text="No selection", fg=MUTED, bg=PANEL_BG,
                                         wraplength=220, justify=tk.LEFT, font=("Segoe UI", 8))
        self.preview_text_lbl.pack(anchor=tk.W)
        self._refresh_folder_view(select_path=self._open_folder)

    def _build_editor_panel(self, parent):
        frame = tk.Frame(parent, bg=PANEL_BG)
        parent.add(frame, minsize=200)

        self._section_label(frame, "File Editor")

        top_row = tk.Frame(frame, bg=PANEL_BG, pady=6, padx=8)
        top_row.pack(side=tk.TOP, fill=tk.X)

        self.file_path_lbl = tk.Label(
            top_row, text="No file selected", fg=MUTED, bg=PANEL_BG,
            font=("Segoe UI", 8), wraplength=220, justify=tk.LEFT,
        )
        self.file_path_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(
            top_row, text="Save File", command=self._save_selected_file,
            bg=INPUT_BG, fg=GREEN, relief=tk.FLAT,
            font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2",
        ).pack(side=tk.RIGHT)

        self.editor_box = tk.Text(
            frame, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
            relief=tk.FLAT, font=("Consolas", 11), wrap=tk.WORD,
            padx=10, pady=10, undo=True,
        )
        self.editor_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
        self.editor_box.bind("<Control-s>", self._save_selected_file)
        self.root.bind("<Delete>", self._delete_selected_item)

        self._selected_file_path = ""

    def _build_command_panel(self, parent):
        frame = tk.Frame(parent, bg=PANEL_BG)
        parent.add(frame, minsize=180)

        self._section_label(frame, "명령 입력")

        btn_row = tk.Frame(frame, bg=PANEL_BG, pady=6, padx=8)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X)

        left_actions = tk.Frame(btn_row, bg=PANEL_BG)
        left_actions.pack(side=tk.LEFT, fill=tk.X, expand=True)

        center_actions = tk.Frame(btn_row, bg=PANEL_BG)
        center_actions.pack(side=tk.LEFT)

        right_actions = tk.Frame(btn_row, bg=PANEL_BG)
        right_actions.pack(side=tk.RIGHT)

        self.send_btn = tk.Button(
            left_actions, text="전송  (Ctrl+Enter)", command=self._send,
            bg=BLUE, fg=DARK_BG, relief=tk.FLAT,
            font=("Segoe UI", 10, "bold"), padx=14, pady=3,
            cursor="hand2",
        )
        self.send_btn.pack(side=tk.LEFT, padx=(0, 8))
        ToolTip(self.send_btn, "명령 전송")

        tk.Button(
            left_actions, text="지우기",
            command=lambda: (self.input_box.delete("1.0", tk.END), self._schedule_layout_save()),
            bg=INPUT_BG, fg=MUTED, relief=tk.FLAT,
            font=("Segoe UI", 9), padx=10, pady=3, cursor="hand2",
        ).pack(side=tk.LEFT)

        delete_group = tk.Frame(left_actions, bg=PANEL_BG)
        delete_group.pack(side=tk.LEFT, padx=(2, 0))

        self.cancel_btn = tk.Button(
            delete_group, text="취소", command=self._cancel_current_job,
            bg=INPUT_BG, fg=MUTED, relief=tk.FLAT,
            font=("Segoe UI", 9), padx=10, pady=3, cursor="hand2",
            state=tk.DISABLED,
        )
        self.cancel_btn.pack(side=tk.LEFT)
        ToolTip(self.cancel_btn, "현재 요청 취소")

        self.approve_btn = tk.Button(
            center_actions, text="권한허용", command=self._approve_pending_command,
            bg=INPUT_BG, fg=MUTED, relief=tk.FLAT,
            font=("Segoe UI", 9), padx=10, pady=3, cursor="hand2",
            state=tk.DISABLED,
        )
        self.approve_btn.pack(side=tk.LEFT, padx=(0, 6))
        ToolTip(self.approve_btn, "에이전트 권한 허용")

        self.mode_btn = tk.Button(
            center_actions, text="채팅 모드", command=self._toggle_mode,
            bg="#1a1e2e", fg="#bc8cff", relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"), padx=12, pady=3,
            cursor="hand2",
        )
        self.mode_btn.pack(side=tk.LEFT)
        ToolTip(self.mode_btn, "채팅 모드 / 에이전트 모드 전환")

        self.mode_indicator = tk.Label(
            center_actions, text="", fg=MUTED, bg=PANEL_BG,
            font=("Segoe UI", 8),
        )
        self.mode_indicator.pack(side=tk.LEFT, padx=(6, 0))

        self.turn_lbl = tk.Label(right_actions, text="대화: 0턴",
                                 fg=MUTED, bg=PANEL_BG,
                                 font=("Segoe UI", 9))
        self.turn_lbl.pack(side=tk.RIGHT)

        self.input_box = tk.Text(
            frame, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
            relief=tk.FLAT, font=("Consolas", 11), wrap=tk.WORD,
            padx=10, pady=10, undo=True,
        )
        self.input_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
        self.input_box.bind("<KeyRelease>", self._on_input_changed)
        self.input_box.bind("<Control-Return>", lambda e: self._send())
        self.input_box.bind("<Control-v>", self._paste_from_clipboard)
        self.input_box.bind("<Control-V>", self._paste_from_clipboard)
        self.input_box.bind("<<Paste>>", self._paste_from_clipboard)

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
        self.input_box.bind("<Control-v>", self._paste_from_clipboard)
        self.input_box.bind("<Control-V>", self._paste_from_clipboard)
        self.input_box.bind("<<Paste>>", self._paste_from_clipboard)

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

    def _parse_response_files(self, text: str) -> list[tuple[str, str]]:
        files: list[tuple[str, str]] = []
        lines = text.splitlines()
        current_path = ""
        current_block: list[str] = []
        in_block = False
        pending_file_hint = ""

        def flush_block():
            nonlocal current_path, current_block, in_block, pending_file_hint
            if current_path and current_block:
                content = "\n".join(current_block).rstrip("\n")
                files.append((current_path, content))
            current_path = ""
            current_block = []
            in_block = False
            pending_file_hint = ""

        for line in lines:
            stripped = line.strip()
            file_match = re.match(r"^(?:#{1,6}\s*)?(?:File|파일|Path|경로)\s*[:=]\s*(.+)$", stripped, re.IGNORECASE)
            if file_match:
                flush_block()
                current_path = file_match.group(1).strip().strip("`")
                continue

            header_match = re.match(r"^#{1,6}\s+(.+\.(?:cs|csproj|sln|json|xml|xaml|resx|config|txt|md|ps1|py|js|ts|html|css|csproj))\s*$", stripped, re.IGNORECASE)
            if header_match and not in_block:
                flush_block()
                current_path = header_match.group(1).strip()
                continue

            if stripped.startswith("```"):
                fence_hint = stripped[3:].strip().strip("`")
                if in_block:
                    flush_block()
                else:
                    in_block = True
                    current_block = []
                    if fence_hint:
                        pending_file_hint = fence_hint
                        if not current_path:
                            current_path = fence_hint
                continue

            if in_block:
                current_block.append(line)

        flush_block()

        # Fall back to fence-hinted blocks if they were not explicitly captured as paths.
        if not files and pending_file_hint and current_block:
            files.append((pending_file_hint, "\n".join(current_block).rstrip("\n")))
        return files

    def _save_response_files(self, response: str):
        base = self._open_folder or PROJECT_ROOT
        targets = self._parse_response_files(response)
        saved = []
        for rel_path, content in targets:
            rel_path = rel_path.strip().replace("/", os.sep).replace("\\", os.sep)
            if not rel_path:
                continue
            abs_path = os.path.abspath(os.path.join(base, rel_path))
            if not abs_path.startswith(os.path.abspath(base)):
                continue
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content.rstrip("\n") + "\n")
            saved.append(abs_path)

        if saved:
            self._refresh_folder_view()
            if saved:
                self._select_tree_path(os.path.dirname(saved[0]))
            self._context_injected = False
            self.result_box.config(state=tk.NORMAL)
            self.result_box.insert(tk.END, "\n\n[Saved files]\n", "agent_ok")
            for path in saved:
                self.result_box.insert(tk.END, f"- {path}\n", "agent_step")
            self.result_box.config(state=tk.DISABLED)
            self.result_box.see(tk.END)
        return saved

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
        # P4-3: in-flight 가드 — 이미 요청이 진행 중이면 두 번째 클릭을 차단한다.
        # 수동 검증 시나리오: Send 버튼을 연속으로 두 번 클릭하면 첫 번째만 처리되고
        # 두 번째는 여기서 즉시 반환되어 서버에 요청이 중복 전송되지 않는다.
        if self._inflight:
            return
        if self._sending:
            return
        prompt = self.input_box.get("1.0", tk.END).strip()
        if not prompt:
            return
        prompt = self._build_prompt_with_context(prompt)

        self._sending = True
        self._inflight = True  # P4-3: 요청 시작
        self._cancel_requested = False
        # P4-3: 버튼을 회색으로 처리해 in-flight 상태임을 시각적으로 표시
        self.send_btn.config(
            state=tk.DISABLED,
            text="생성 중...",
            bg="#4a4a4a",   # 회색 — in-flight 시각적 피드백
            fg="#9a9a9a",
            cursor="arrow",
        )
        self.approve_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self._pending_approval_command = ""
        self._set_text(self.copy_box, "")
        self.elapsed_lbl.config(text="")
        self.status_bar.config(text="요청 전송 중")

        # 생성 중 표시
        self.result_box.config(state=tk.NORMAL)
        if len(self.result_box.get("1.0", tk.END).strip()) > 0:
            self.result_box.insert(tk.END, "\n")

        self._schedule_layout_save()

        self._save_state()

        if self._agent_mode:
            self.result_box.insert(tk.END, "⏳ 에이전트 실행 중...\n", "agent_thought")
        else:
            self.result_box.insert(tk.END, "⏳ 생성 중입니다...\n", "normal")
        self.result_box.config(state=tk.DISABLED)
        self.result_box.see(tk.END)
        self._begin_busy_indicator("승인 명령 실행 중")
        self._begin_busy_indicator("요청 전송 중")

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
            response_parts = []
            token_count = 0
            self.root.after(0, lambda: self._chat_stream_begin(prompt))
            with requests.post(f"{API_URL}/chat/stream", json=payload, stream=True, timeout=(10, 600)) as r:
                self._active_stream_response = r
                r.raise_for_status()
                elapsed = 0
                for raw in r.iter_lines(decode_unicode=True):
                    if self._cancel_requested:
                        break
                    if not raw:
                        continue
                    try:
                        evt = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    t = evt.get("type")
                    if t == "token":
                        token = evt.get("text", "")
                        response_parts.append(token)
                        token_count += 1
                        self.root.after(0, lambda tok=token: self._chat_stream_token(tok))
                    elif t == "heartbeat":
                        self.root.after(0, lambda n=token_count: self._chat_stream_heartbeat(n))
                    elif t == "final":
                        response = evt.get("response", "".join(response_parts))
                        elapsed = evt.get("elapsed_ms", 0)
                        self.root.after(0, lambda resp=response, el=elapsed, n=token_count: self._chat_stream_final(resp, el, n))
                        break
                    elif t == "error":
                        self.root.after(0, lambda m=evt.get("error", "error"): self._on_error(m))
                        break
        except Exception as e:
            self.root.after(0, lambda err=str(e): self._on_error(err))
        finally:
            self._active_stream_response = None
            self.root.after(0, self._done_sending)

    def _run_agent(self, prompt: str):
        """에이전트 모드 — /agent/stream 엔드포인트 스트리밍 수신"""
        try:
            payload = {
                "message": prompt,
                "session_id": self._agent_session_id,
                "working_dir": self._open_folder or PROJECT_ROOT,
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
                self._active_stream_response = r
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
                        self.root.after(0, lambda n=getattr(self, "_agent_step_count", 0): self._agent_stream_heartbeat(n))
                    elif t == "final":
                        answer = evt.get("answer", "")
                        elapsed = evt.get("elapsed_ms", 0)
                        self.root.after(0, lambda a=answer, e=elapsed, n=getattr(self, "_agent_step_count", 0): self._agent_stream_final(a, e, n))
                    elif t == "error":
                        err = evt.get("error", "알 수 없는 오류")
                        self.root.after(0, lambda m=err: self._on_error(m))

        except Exception as e:
            self.root.after(0, lambda err=str(e): self._on_error(err))
        finally:
            self._active_stream_response = None
            self.root.after(0, self._done_sending)

    def _begin_busy_indicator(self, label: str):
        self._busy_label = label
        self._busy_started_at = time.time()
        self._busy_tick()

    def _busy_tick(self):
        if not self._sending:
            return
        elapsed = int(time.time() - getattr(self, "_busy_started_at", time.time()))
        label = getattr(self, "_busy_label", "진행 중")
        self.elapsed_lbl.config(text=f"{label}... {elapsed}s")
        self.root.after(1000, self._busy_tick)

    def _schedule_buffer_flush(self):
        if self._buffer_flush_job is not None:
            return
        self._buffer_flush_job = self.root.after(50, self._flush_stream_buffers)

    def _flush_stream_buffers(self):
        self._buffer_flush_job = None
        if self._cancel_requested:
            self._chat_text_buffer.clear()
            self._agent_step_buffer.clear()
            return

        if self._chat_text_buffer:
            text = "".join(self._chat_text_buffer)
            self._chat_text_buffer.clear()
            self.result_box.config(state=tk.NORMAL)
            self.result_box.insert(tk.END, text, "normal")
            self.result_box.config(state=tk.DISABLED)
            self.result_box.see(tk.END)

        if self._agent_step_buffer:
            pending = self._agent_step_buffer[:]
            self._agent_step_buffer.clear()
            self.result_box.config(state=tk.NORMAL)
            for step in pending:
                self._render_agent_step(step)
            self.result_box.config(state=tk.DISABLED)
            self.result_box.see(tk.END)

        if self._chat_text_buffer or self._agent_step_buffer:
            self._schedule_buffer_flush()

    def _chat_stream_begin(self, prompt: str):
        self.status_bar.config(text="채팅 응답 생성 중", bg="#1f4d2e", fg=GREEN)
        self.elapsed_lbl.config(text="0초 / 0토큰")
        self.result_box.config(state=tk.NORMAL)
        self.result_box.insert(tk.END, "\nSm_AICoder ▶ ", "ai_header")
        self.result_box.insert(tk.END, "\n", "normal")
        self.result_box.config(state=tk.DISABLED)

    def _chat_stream_token(self, token: str):
        if self._cancel_requested:
            return
        self._chat_text_buffer.append(token)
        self._schedule_buffer_flush()

    def _chat_stream_heartbeat(self, token_count: int = 0):
        elapsed = int(time.time() - getattr(self, "_busy_started_at", time.time()))
        self.status_bar.config(text=f"채팅 응답 생성 중... {elapsed}s", bg="#1f4d2e", fg=GREEN)
        self.elapsed_lbl.config(text=f"{elapsed}초 / {token_count}토큰")

    def _chat_stream_final(self, response: str, elapsed_ms: int, token_count: int = 0):
        if self._cancel_requested:
            return
        self._flush_stream_buffers()
        code = self._extract_code(response)
        self.history.append({"role": "user", "content": self.input_box.get("1.0", tk.END).strip()})
        self.history.append({"role": "assistant", "content": response})
        self._append_message("assistant", response)
        self._save_response_files(response)
        self._set_text(self.copy_box, code)
        self.elapsed_lbl.config(text=f"{elapsed_ms / 1000:.1f}초 / {token_count}토큰")
        self.status_bar.config(text="완료", bg="#1f2937", fg=TEXT)

        self._save_state()

    def _cancel_current_job(self):
        self._cancel_requested = True
        stream = self._active_stream_response
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
            self._active_stream_response = None
        if self._agent_mode:
            try:
                requests.post(
                    f"{API_URL}/agent/cancel",
                    params={"session_id": self._agent_session_id},
                    timeout=5,
                )
            except Exception:
                pass
        self.status_bar.config(text="취소 요청됨", bg="#7f1d1d", fg="#fca5a5")
        # P4-3: 취소 시에도 in-flight 해제 후 버튼 색상 복원
        self._inflight = False
        self._sending = False
        if self._agent_mode:
            self.send_btn.config(
                state=tk.NORMAL,
                text="전송  (Ctrl+Enter)",
                bg="#bc8cff",
                fg=DARK_BG,
                cursor="hand2",
            )
        else:
            self.send_btn.config(
                state=tk.NORMAL,
                text="전송  (Ctrl+Enter)",
                bg=BLUE,
                fg=DARK_BG,
                cursor="hand2",
            )
        self.cancel_btn.config(state=tk.DISABLED)

    def _on_response(self, response, code, elapsed_ms):
        # 사용자 질문 추가
        if len(self.history) >= 2:
            user_msg = self.history[-2]["content"]
            self._append_message("user", user_msg)

        # AI 응답 추가
        self._append_message("assistant", response)
        self._save_response_files(response)

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
        self.elapsed_lbl.config(text="⏳ 실행 중... / 0단계")
        self.status_bar.config(text="에이전트 실행 중", bg="#1a365d", fg="#93c5fd")

    def _agent_stream_step(self, step: dict):
        """스트리밍 단계 이벤트 — 즉시 ③ 창에 추가.

        P4-1: step{"kind":"token", "n":int} 이벤트는 result_box 에 렌더하지 않고
              elapsed_lbl 의 토큰 카운터만 갱신한다. 렌더하면 수백 줄의 미완성 JSON
              조각이 창에 쌓이기 때문이다.
        """
        # P4-1: token step — 화면에 표시하지 않고 카운터만 갱신
        if step.get("kind") == "token" or step.get("type") == "token":
            n = step.get("n", 0)
            elapsed = int(time.time() - getattr(self, "_busy_started_at", time.time()))
            self.elapsed_lbl.config(text=f"생성중 {n} 토큰... {elapsed}s")
            self._agent_last_beat = time.time()
            return

        self.result_box.config(state=tk.NORMAL)
        self._render_agent_step(step)
        self.result_box.config(state=tk.DISABLED)
        self.result_box.see(tk.END)

        self._agent_step_count = getattr(self, "_agent_step_count", 0) + 1
        self._agent_last_beat = time.time()

    def _agent_stream_heartbeat(self, step_count: int = 0):
        """2초마다 서버가 살아있음을 알림 — 상단 경과 표시 갱신"""
        self._agent_last_beat = time.time()
        n = step_count or getattr(self, "_agent_step_count", 0)
        self.elapsed_lbl.config(text=f"⏳ 실행 중... ({n}단계)")
        self.status_bar.config(text=f"에이전트 실행 중... {n}단계", bg="#1a365d", fg="#93c5fd")

    def _agent_stream_final(self, answer: str, elapsed_ms: int, step_count: int = 0):
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
        n = step_count or getattr(self, "_agent_step_count", 0)
        self.elapsed_lbl.config(text=f"{elapsed_ms / 1000:.1f}초 ({n}단계)")
        self.status_bar.config(text="완료", bg="#1f2937", fg=TEXT)

        self._save_state()

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

        elif step_type == "approval_required":
            cmd = step.get("command", "")
            msg = step.get("message", "Permission approval required")
            self._pending_approval_command = cmd
            self._pending_approval_timeout = int(step.get("timeout", 30) or 30)
            if self._always_approve:
                self.root.after(0, self._approve_pending_command)
            else:
                self.root.after(0, lambda c=cmd, m=msg: self._show_approval_dialog(c, m))
            self.result_box.insert(tk.END, "      [APPROVAL REQUIRED] ", "agent_fail")
            self.result_box.insert(tk.END, f"{cmd}\n", "agent_step")
            self.result_box.insert(tk.END, f"      {msg}\n", "agent_fail")

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
        self._inflight = False  # P4-3: in-flight 해제 — 다음 Send 클릭 허용
        # 모드별로 원래 버튼 색상 복원
        if self._agent_mode:
            self.send_btn.config(
                state=tk.NORMAL,
                text="전송  (Ctrl+Enter)",
                bg="#bc8cff",
                fg=DARK_BG,
                cursor="hand2",
            )
        else:
            self.send_btn.config(
                state=tk.NORMAL,
                text="전송  (Ctrl+Enter)",
                bg=BLUE,
                fg=DARK_BG,
                cursor="hand2",
            )
        self.cancel_btn.config(state=tk.DISABLED)

    def _show_approval_dialog(self, command: str, message: str):
        if self._approval_dialog is not None and self._approval_dialog.winfo_exists():
            try:
                self._approval_dialog.lift()
                self._approval_dialog.focus_force()
                return
            except Exception:
                self._approval_dialog = None

        dlg = tk.Toplevel(self.root)
        dlg.title("Command Approval")
        dlg.configure(bg=PANEL_BG)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        self._approval_dialog = dlg

        tk.Label(dlg, text="권한이 필요한 명령이 차단되었습니다.", fg=BLUE, bg=PANEL_BG,
                 font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=16, pady=(14, 6))
        tk.Label(dlg, text=message, fg=TEXT, bg=PANEL_BG, wraplength=520,
                 justify=tk.LEFT, font=("Segoe UI", 9)).pack(anchor=tk.W, padx=16, pady=(0, 10))
        tk.Label(dlg, text="명령", fg=MUTED, bg=PANEL_BG, font=("Segoe UI", 8)).pack(anchor=tk.W, padx=16)

        cmd_box = tk.Text(
            dlg, height=5, width=72, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
            relief=tk.FLAT, font=("Consolas", 9), wrap=tk.WORD,
        )
        cmd_box.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 12))
        cmd_box.insert("1.0", command)
        cmd_box.config(state=tk.DISABLED)

        always_var = tk.BooleanVar(value=self._always_approve)
        chk = tk.Checkbutton(
            dlg,
            text="항상 승인",
            variable=always_var,
            onvalue=True,
            offvalue=False,
            bg=PANEL_BG,
            fg=TEXT,
            selectcolor=PANEL_BG,
            activebackground=PANEL_BG,
            activeforeground=TEXT,
            font=("Segoe UI", 9),
        )
        chk.pack(anchor=tk.W, padx=14, pady=(0, 10))

        btn_row = tk.Frame(dlg, bg=PANEL_BG)
        btn_row.pack(fill=tk.X, padx=16, pady=(0, 14))

        tk.Button(
            btn_row, text="거부", command=lambda: self._close_approval_dialog(False),
            bg=INPUT_BG, fg=MUTED, relief=tk.FLAT, font=("Segoe UI", 9), padx=12, pady=4,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(
            btn_row, text="허용", command=lambda: self._close_approval_dialog(True, always_var.get()),
            bg="#1f4d2e", fg=GREEN, relief=tk.FLAT, font=("Segoe UI", 9, "bold"), padx=12, pady=4,
        ).pack(side=tk.RIGHT)

        dlg.protocol("WM_DELETE_WINDOW", lambda: self._close_approval_dialog(False, always_var.get()))
        dlg.update_idletasks()
        x = self.root.winfo_rootx() + 80
        y = self.root.winfo_rooty() + 80
        dlg.geometry(f"+{x}+{y}")

    def _close_approval_dialog(self, approved: bool, always_approve: bool = False):
        dlg = self._approval_dialog
        if dlg is not None and dlg.winfo_exists():
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()
        self._approval_dialog = None

        if approved:
            self._always_approve = bool(always_approve)
            self._save_layout()
            self._approve_pending_command()
        else:
            self._pending_approval_command = ""
            self.approve_btn.config(state=tk.DISABLED)

    def _approve_pending_command(self):
        command = self._pending_approval_command.strip()
        if not command:
            return

        self.approve_btn.config(state=tk.DISABLED)
        self.status_bar.config(text="권한 승인 중")

        self.result_box.config(state=tk.NORMAL)
        self.result_box.insert(tk.END, f"\n[권한허용 요청] {command}\n", "agent_ok")
        self.result_box.config(state=tk.DISABLED)
        self.result_box.see(tk.END)

        def worker():
            try:
                payload = {
                    "session_id": self._agent_session_id,
                    "command": command,
                    "timeout": self._pending_approval_timeout,
                }
                r = requests.post(f"{API_URL}/agent/approve", json=payload, timeout=(10, 600))
                r.raise_for_status()
                data = r.json()
                result_text = data.get("result", "")
                self.root.after(0, lambda: self._append_message("assistant", result_text))
                self.root.after(0, lambda: self.status_bar.config(text="권한 승인 완료"))
                self._pending_approval_command = ""
            except requests.exceptions.ReadTimeout:
                self.root.after(
                    0,
                    lambda: self._on_error(
                        "승인된 명령 실행이 너무 오래 걸립니다. "
                        "서버 로그를 확인하거나 timeout을 더 늘려야 합니다."
                    ),
                )
            except Exception as e:
                self.root.after(0, lambda err=str(e): self._on_error(err))
            finally:
                self.root.after(0, lambda: self.approve_btn.config(state=tk.NORMAL if self._pending_approval_command else tk.DISABLED))

        threading.Thread(target=worker, daemon=True).start()

    def _copy_code(self):
        text = self.copy_box.get("1.0", tk.END).strip()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.copy_btn.config(text="Copied")
        self.root.after(2000, lambda: self.copy_btn.config(text="Copy Code"))

    def _open_folder_dialog(self):
        folder = filedialog.askdirectory(initialdir=self._open_folder or PROJECT_ROOT, title="Open Folder")
        if not folder:
            return
        self._open_folder = os.path.abspath(folder)
        self.folder_path_lbl.config(text=self._open_folder)
        self._context_injected = False   # P2-1: 새 폴더 열면 컨텍스트 플래그 리셋
        self._refresh_folder_view(select_path=self._open_folder)
        self._save_layout()

    def _create_file(self):
        base = self._open_folder or PROJECT_ROOT
        name = simpledialog.askstring("New File", "File name relative to OpenFolder:", parent=self.root)
        if not name:
            return
        target = os.path.abspath(os.path.join(base, name))
        if not target.startswith(os.path.abspath(base)):
            messagebox.showerror("Invalid Path", "File must be inside OpenFolder.")
            return
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if not os.path.exists(target):
            with open(target, "w", encoding="utf-8") as f:
                f.write("")
        self._refresh_folder_view(select_path=target)

    def _create_folder(self):
        base = self._open_folder or PROJECT_ROOT
        name = simpledialog.askstring("New Folder", "Folder name relative to OpenFolder:", parent=self.root)
        if not name:
            return
        target = os.path.abspath(os.path.join(base, name))
        if not target.startswith(os.path.abspath(base)):
            messagebox.showerror("Invalid Path", "Folder must be inside OpenFolder.")
            return
        os.makedirs(target, exist_ok=True)
        self._refresh_folder_view(select_path=target)

    def _delete_selected_item(self):
        path = ""
        if hasattr(self, "folder_tree"):
            sel = self.folder_tree.focus()
            path = self._tree_nodes.get(sel, "")
        if not path and self._selected_file_path:
            path = self._selected_file_path
        if not path:
            messagebox.showwarning("No selection", "Select a file or folder to delete.")
            return

        base = os.path.abspath(self._open_folder or PROJECT_ROOT)
        target = os.path.abspath(path)
        if target == base:
            messagebox.showwarning("Not allowed", "OpenFolder root cannot be deleted.")
            return
        if not target.startswith(base + os.sep):
            messagebox.showwarning("Not allowed", "Selected item is outside OpenFolder.")
            return

        if os.path.isdir(target):
            has_children = False
            try:
                has_children = len(os.listdir(target)) > 0
            except Exception:
                has_children = True
            prompt = "하위 항목까지 모두 삭제하시겠습니까?" if has_children else "빈 폴더를 삭제하시겠습니까?"
            ok = messagebox.askyesno("폴더 삭제", f"{prompt}\n\n{target}", parent=self.root)
            if not ok:
                return
            try:
                import shutil
                shutil.rmtree(target)
            except Exception as e:
                messagebox.showerror("Delete failed", str(e))
                return
        else:
            ok = messagebox.askyesno("파일 삭제", f"파일을 삭제하시겠습니까?\n\n{target}", parent=self.root)
            if not ok:
                return
            try:
                os.remove(target)
            except Exception as e:
                messagebox.showerror("Delete failed", str(e))
                return

        if self._selected_file_path and os.path.abspath(self._selected_file_path) == target:
            self._selected_file_path = ""
            self.file_path_lbl.config(text="No file selected")
            self.editor_box.delete("1.0", tk.END)
        self._refresh_folder_view(select_path=os.path.dirname(target))

    def _refresh_folder_view(self, select_path=None):
        if not hasattr(self, "folder_tree"):
            return
        base = self._open_folder or PROJECT_ROOT
        self.folder_path_lbl.config(text=base)
        self.folder_tree.delete(*self.folder_tree.get_children())
        self._folder_rows = []
        self._tree_nodes = {}
        try:
            self._insert_tree_node("", base, base, 0, max_depth=4)
            if select_path:
                self.root.after_idle(lambda p=os.path.abspath(select_path): self._select_tree_path(p))
        except Exception as e:
            self.preview_text_lbl.config(text=f"Error: {e}")

    def _select_tree_path(self, target_path: str):
        if not hasattr(self, "folder_tree") or not target_path:
            return
        target_path = os.path.abspath(target_path)
        for node_id, path in self._tree_nodes.items():
            if os.path.abspath(path) == target_path:
                try:
                    parent = self.folder_tree.parent(node_id)
                    while parent:
                        self.folder_tree.item(parent, open=True)
                        parent = self.folder_tree.parent(parent)
                    self.folder_tree.selection_set(node_id)
                    self.folder_tree.focus(node_id)
                    self.folder_tree.see(node_id)
                except Exception:
                    pass
                break

    def _insert_tree_node(self, parent_id: str, path: str, base: str, depth: int, max_depth: int = 4):
        if depth > max_depth:
            return
        try:
            entries = sorted(os.listdir(path), key=lambda p: (not os.path.isdir(os.path.join(path, p)), p.lower()))
        except Exception:
            entries = []
        ignore = {".git", "__pycache__", "venv", "node_modules", ".sm_aicoder_assets"}
        for name in entries:
            if name in ignore:
                continue
            full = os.path.join(path, name)
            rel = os.path.relpath(full, base)
            node_id = self.folder_tree.insert(parent_id, tk.END, text=name, open=False)
            self._tree_nodes[node_id] = full
            self._folder_rows.append(full)
            if os.path.isdir(full):
                if depth < max_depth:
                    self.folder_tree.insert(node_id, tk.END, text="loading")
            else:
                pass

    def _on_tree_open(self, event=None):
        node = self.folder_tree.focus()
        path = self._tree_nodes.get(node)
        if not path or not os.path.isdir(path):
            return
        children = self.folder_tree.get_children(node)
        if len(children) == 1 and self.folder_tree.item(children[0], "text") == "loading":
            self.folder_tree.delete(children[0])
            self._insert_tree_node(node, path, self._open_folder or PROJECT_ROOT, self._tree_depth(node) + 1)

    def _tree_depth(self, node_id: str) -> int:
        depth = 0
        while True:
            parent = self.folder_tree.parent(node_id)
            if not parent:
                return depth
            depth += 1
            node_id = parent

    def _on_tree_select(self, event=None):
        sel = self.folder_tree.focus()
        path = self._tree_nodes.get(sel)
        if not path:
            return
        self._update_preview(path)
        if os.path.isfile(path):
            self._load_attachment_from_file(path)
            self._load_file_into_editor(path)

    def _load_attachment_from_file(self, path: str):
        if path in self._attachments:
            self._update_preview(path)
            return
        self._attachments.append(path)
        self.copy_btn.config(text=f"Attached {len(self._attachments)}")
        self._set_text(self.copy_box, "\n".join(self._attachments))
        self._update_preview(path)

    def _load_file_into_editor(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self._selected_file_path = path
            self.file_path_lbl.config(text=path)
            self.editor_box.delete("1.0", tk.END)
            self.editor_box.insert("1.0", content)
        except Exception as e:
            self.file_path_lbl.config(text=f"Failed to load: {e}")

    def _save_selected_file(self, event=None):
        path = self._selected_file_path
        if not path:
            messagebox.showwarning("No file", "Select a file from OpenFolder first.")
            return "break" if event is not None else None
        try:
            content = self.editor_box.get("1.0", tk.END)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content.rstrip("\n") + "\n")
            self.file_path_lbl.config(text=path)
            self._refresh_folder_view()
            self._update_preview(path)
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
        return "break" if event is not None else None

    def _update_preview(self, path: str):
        if os.path.isdir(path):
            try:
                count = len(os.listdir(path))
            except Exception:
                count = 0
            self.preview_image_lbl.config(image="", text="")
            self.preview_text_lbl.config(text=f"Folder: {path}\nItems: {count}")
            return

        ext = os.path.splitext(path)[1].lower()
        if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"} and Image is not None and ImageTk is not None:
            try:
                img = Image.open(path)
                img.thumbnail((260, 160))
                self._preview_image = ImageTk.PhotoImage(img)
                self.preview_image_lbl.config(image=self._preview_image, text="")
                self.preview_text_lbl.config(text=os.path.basename(path))
                return
            except Exception:
                pass

        self.preview_image_lbl.config(image="", text="")
        info = self._read_file_summary(path)
        self.preview_text_lbl.config(text=info)

    def _paste_from_clipboard(self, event=None):
        if ImageGrab is None:
            return
        try:
            data = ImageGrab.grabclipboard()
        except Exception:
            return

        if isinstance(data, list):
            for path in data:
                if os.path.isfile(path):
                    self._load_attachment_from_file(path)
            return "break"

        if hasattr(data, "save"):
            base = self._open_folder or PROJECT_ROOT
            assets = os.path.join(base, ".sm_aicoder_assets")
            os.makedirs(assets, exist_ok=True)
            filename = f"pasted_{int(time.time())}.png"
            target = os.path.join(assets, filename)
            data.save(target, "PNG")
            self._load_attachment_from_file(target)
            messagebox.showinfo("Pasted Image", f"Clipboard image saved to:\n{target}")
            return "break"

        return None

    def _read_file_summary(self, path: str) -> str:
        try:
            size = os.path.getsize(path)
            ext = os.path.splitext(path)[1].lower() or "no ext"
            if size > 50_000:
                return f"{os.path.basename(path)}\n{ext}\n{size} bytes\nToo large to preview"
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.read().splitlines()
            head = lines[:4]                # P2-2: 8→4
            text = "\n".join(head)
            if len(lines) > 4:
                text += "\n..."
            return f"{os.path.basename(path)}\n{ext}\n{size} bytes\n\n{text}".strip()
        except Exception as e:
            return f"{os.path.basename(path)}\nPreview unavailable: {e}"

    def _build_prompt_with_context(self, prompt: str) -> str:
        # P2-1: 첫 턴(또는 새 폴더)에만 폴더 트리/파일 요약을 주입한다.
        # 두 번째 턴부터는 선택 파일 내용과 첨부만 포함.
        base = self._open_folder or PROJECT_ROOT
        lines: list[str] = []

        if not self._context_injected:
            # ── 첫 턴 전용 컨텍스트 ──────────────────────────────
            lines += [f"[OpenFolder] {base}", "[Folder files]"]
            for row in self._folder_rows[:50]:          # P2-2: 200→50
                try:
                    rel = os.path.relpath(row, base)
                except Exception:
                    rel = row
                lines.append(f"- {rel}")
            lines.append("")
            lines.append("[Folder summaries]")
            for path in self._folder_rows[:5]:          # P2-2: 12→5
                if os.path.isfile(path):
                    lines.append(self._read_file_summary(path))
                    lines.append("")
            self._context_injected = True

        # ── 매 턴 포함: 선택 파일 내용 ──────────────────────────
        if self._selected_file_path:
            lines.append(f"[Selected file] {self._selected_file_path}")
            try:
                editor_text = self.editor_box.get("1.0", tk.END).rstrip()
            except Exception:
                editor_text = ""
            if editor_text:
                lines.append("[Selected file content]")
                lines.append(editor_text)
                lines.append("")

        if self._attachments:
            lines.append("[Attachments]")
            lines.extend(f"- {p}" for p in self._attachments)

        lines.append("")
        lines.append(prompt)
        return "\n".join(lines)

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
        self._save_state()
        self._apply_mode_ui()

    def _apply_mode_ui(self):
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
