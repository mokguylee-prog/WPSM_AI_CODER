"""백그라운드 서버 런처 — start_server.ps1에서 호출"""
import subprocess
import sys
import os
import time

PID_FILE = "server.pid"
LOG_OUT = "server_out.log"
LOG_ERR = "server_err.log"


def is_running(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        # psutil 없으면 os.kill(0) 방식으로 확인
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def start():
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            pid_str = f.read().strip()
        try:
            pid = int(pid_str)
        except ValueError:
            pid = None

        if pid and is_running(pid):
            print(f"서버가 이미 실행 중입니다 (PID: {pid})")
            print("stop_server.ps1 로 먼저 종료하세요.")
            return
        else:
            # 프로세스가 없는데 pid 파일만 남은 경우 — 자동 정리
            os.remove(PID_FILE)
            print(f"이전 서버 잔여 파일 정리 완료 (PID: {pid_str})")

    with open(LOG_OUT, "w") as out, open(LOG_ERR, "w") as err:
        proc = subprocess.Popen(
            [sys.executable, "scripts/api_server.py"],
            stdout=out,
            stderr=err,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )

    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))

    print(f"서버 시작 (PID: {proc.pid})")
    print(f"로그: {LOG_OUT} / {LOG_ERR}")
    print("모델 로딩에 30~60초 소요됩니다...")

    # 최대 90초 대기 (내장 urllib 사용 — 외부 패키지 불필요)
    import urllib.request
    import json as _json
    for i in range(90):
        time.sleep(1)
        try:
            with urllib.request.urlopen("http://localhost:8888/health", timeout=2) as resp:
                data = _json.loads(resp.read())
                model = data.get("model", "")
                print(f"서버 준비 완료 — 모델: {model}")
                return
        except Exception:
            pass
        if i % 10 == 9:
            print(f"  대기 중... ({i+1}초)")

    print("서버 시작 시간 초과. server_err.log 를 확인하세요.")


if __name__ == "__main__":
    start()
