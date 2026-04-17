"""Background server launcher used by start_server.ps1/start_gui.ps1."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SERVER_DIR)
API_SERVER = os.path.join(SERVER_DIR, "scripts", "api_server.py")
PID_FILE = os.path.join(SERVER_DIR, "server.pid")
LOG_OUT = os.path.join(SERVER_DIR, "server_out.log")
LOG_ERR = os.path.join(SERVER_DIR, "server_err.log")
PORT = 8888


def is_running(pid: int) -> bool:
    """Return True if the process id exists."""
    try:
        import psutil

        return psutil.pid_exists(pid)
    except ImportError:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def get_listener_pid(port: int = PORT) -> int | None:
    """Return the LISTENING PID on given port, if any."""
    try:
        import psutil

        for conn in psutil.net_connections(kind="inet"):
            if conn.status == "LISTEN" and conn.laddr and conn.laddr.port == port and conn.pid:
                return int(conn.pid)
    except Exception:
        pass

    # Fallback: parse netstat output
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, encoding="utf-8", errors="ignore")
        for line in out.splitlines():
            line = line.strip()
            if f":{port}" in line and "LISTENING" in line:
                parts = [p for p in line.split() if p]
                if parts:
                    return int(parts[-1])
    except Exception:
        pass

    return None


def read_pid_file() -> int | None:
    if not os.path.exists(PID_FILE):
        return None
    try:
        raw = open(PID_FILE, "r", encoding="utf-8").read().strip()
        return int(raw) if raw else None
    except Exception:
        return None


def write_pid_file(pid: int):
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(pid))


def wait_for_health(timeout_sec: int = 90) -> dict | None:
    """Wait for /health and return decoded payload on success."""
    for i in range(timeout_sec):
        time.sleep(1)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as resp:
                return json.loads(resp.read())
        except Exception:
            pass
        if i % 10 == 9:
            print(f"  waiting... ({i + 1}s)")
    return None


def start():
    existing_listener = get_listener_pid(PORT)
    if existing_listener and is_running(existing_listener):
        print(f"Server already listening on :{PORT} (PID: {existing_listener})")
        write_pid_file(existing_listener)
        return

    existing_pid = read_pid_file()
    if existing_pid and is_running(existing_pid):
        print(f"Server process already running (PID from file: {existing_pid})")
        return
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
        print("Removed stale server.pid")

    with open(LOG_OUT, "w", encoding="utf-8") as out, open(LOG_ERR, "w", encoding="utf-8") as err:
        proc = subprocess.Popen(
            [sys.executable, API_SERVER],
            stdout=out,
            stderr=err,
            cwd=PROJECT_ROOT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )

    # Write the launcher PID first, then replace with real listener PID after health succeeds.
    write_pid_file(proc.pid)
    print(f"Server launch requested (PID: {proc.pid})")
    print(f"Logs: {LOG_OUT} / {LOG_ERR}")
    print("Model loading usually takes 30~60 seconds.")

    health = wait_for_health(timeout_sec=90)
    if not health:
        print("Server startup timed out. Check server_err.log.")
        return

    model = health.get("model", "")
    listener_pid = get_listener_pid(PORT)
    if listener_pid:
        write_pid_file(listener_pid)
        print(f"Server ready. Model: {model} (listener PID: {listener_pid})")
    else:
        print(f"Server ready. Model: {model}")


if __name__ == "__main__":
    start()
