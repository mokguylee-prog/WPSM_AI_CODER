"""Sm_AICoder 에이전트 클라이언트 — 하네스 모드 대화형 CLI

일반 채팅과 다르게, 에이전트가 자동으로:
- 파일을 탐색하고
- 코드를 검색하고
- 패치를 적용하고
- 테스트를 실행합니다

사용자는 자연어로 지시만 하면 됩니다.
"""
import requests
import json
import sys
import os
import time
import uuid

SERVER = "http://localhost:8888"

# ANSI 색상 코드
C_RESET  = "\033[0m"
C_BLUE   = "\033[94m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_GRAY   = "\033[90m"
C_BOLD   = "\033[1m"
C_CYAN   = "\033[96m"


def check_server() -> str:
    try:
        r = requests.get(f"{SERVER}/health", timeout=5)
        r.raise_for_status()
        return r.json().get("model", "unknown")
    except Exception as e:
        print(f"{C_RED}서버에 연결할 수 없습니다: {e}{C_RESET}")
        print("start_server.ps1 로 서버를 먼저 시작하세요.")
        sys.exit(1)


def check_agent() -> bool:
    """에이전트 엔드포인트 존재 여부 확인"""
    try:
        r = requests.get(f"{SERVER}/agent/sessions", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def print_banner(model: str, agent_ok: bool):
    w = 56
    print(f"{C_BLUE}{'='*w}{C_RESET}")
    print(f"{C_BOLD}{C_BLUE}  Sm_AICoder Agent — 코드 에이전트 모드{C_RESET}")
    print(f"{C_GRAY}  모델: {model}{C_RESET}")
    if agent_ok:
        print(f"{C_GREEN}  에이전트 하네스: 활성{C_RESET}")
    else:
        print(f"{C_RED}  에이전트 하네스: 비활성 (기본 채팅 모드로 동작){C_RESET}")
    print(f"{C_BLUE}{'='*w}{C_RESET}")
    print()
    print(f"  {C_GRAY}명령어:{C_RESET}")
    print(f"    {C_CYAN}:quit{C_RESET}     종료")
    print(f"    {C_CYAN}:reset{C_RESET}    세션 초기화")
    print(f"    {C_CYAN}:dir PATH{C_RESET} 작업 디렉토리 변경")
    print(f"    {C_CYAN}:status{C_RESET}   에이전트 상태 확인")
    print(f"    {C_CYAN}:help{C_RESET}     도움말")
    print()


def print_step(step: dict):
    """에이전트 실행 단계를 출력"""
    step_type = step.get("type", "")

    if step_type == "thinking":
        i = step.get("iteration", "?")
        print(f"  {C_GRAY}[{i}단계] 생각 중...{C_RESET}")

    elif step_type == "action":
        thought = step.get("thought", "")
        action = step.get("action", "")
        args = step.get("arguments", {})
        i = step.get("iteration", "?")

        print(f"  {C_YELLOW}[{i}단계] 판단:{C_RESET} {thought}")
        if action == "answer":
            pass  # 최종 답변은 별도 출력
        else:
            args_str = json.dumps(args, ensure_ascii=False)
            if len(args_str) > 120:
                args_str = args_str[:120] + "..."
            print(f"  {C_CYAN}  도구: {action}{C_RESET}({args_str})")

    elif step_type == "tool_result":
        tool = step.get("tool", "")
        ok = step.get("ok", False)
        result = step.get("result", "")
        status = f"{C_GREEN}성공{C_RESET}" if ok else f"{C_RED}실패{C_RESET}"
        print(f"  {C_GRAY}  결과 [{status}{C_GRAY}]: {result[:150]}{C_RESET}")

    elif step_type == "parse_error":
        print(f"  {C_RED}  JSON 파싱 실패 — 재시도 중...{C_RESET}")


def run_agent(message: str, session_id: str, working_dir: str) -> dict:
    """에이전트 API 호출"""
    payload = {
        "message": message,
        "session_id": session_id,
        "working_dir": working_dir,
        "max_iterations": 15,
        "temperature": 0.1,
        "max_tokens": 1024,
    }
    r = requests.post(f"{SERVER}/agent/run", json=payload, timeout=600)
    r.raise_for_status()
    return r.json()


def collect_input() -> str:
    """여러 줄 입력 수집 (빈 줄로 전송)"""
    lines = []
    print(f"\n{C_GREEN}[YOU] >>>{C_RESET} ", end="", flush=True)
    while True:
        try:
            line = input()
        except (KeyboardInterrupt, EOFError):
            if lines:
                break
            raise
        if line == "" and lines:
            break
        if line == "" and not lines:
            continue
        lines.append(line)
    return "\n".join(lines)


def main():
    model = check_server()
    agent_ok = check_agent()
    print_banner(model, agent_ok)

    session_id = f"cli-{uuid.uuid4().hex[:12]}"
    last_agent_ok = agent_ok
    working_dir = os.getcwd()

    while True:
        try:
            user_input = collect_input()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C_GRAY}종료합니다.{C_RESET}")
            break

        cmd = user_input.strip().lower()

        if cmd == ":quit":
            print(f"{C_GRAY}종료합니다.{C_RESET}")
            break
        elif cmd == ":reset":
            try:
                requests.post(f"{SERVER}/agent/reset", params={"session_id": session_id}, timeout=5)
            except Exception:
                pass
            print(f"{C_GREEN}세션 초기화 완료.{C_RESET}")
            continue
        elif cmd.startswith(":dir "):
            new_dir = user_input.strip()[5:].strip()
            if os.path.isdir(new_dir):
                working_dir = os.path.abspath(new_dir)
                print(f"{C_GREEN}작업 디렉토리: {working_dir}{C_RESET}")
            else:
                print(f"{C_RED}디렉토리 없음: {new_dir}{C_RESET}")
            continue
        elif cmd == ":status":
            try:
                r = requests.get(f"{SERVER}/agent/sessions", timeout=5)
                sessions = r.json().get("sessions", [])
                if sessions:
                    for s in sessions:
                        print(f"  세션: {s['session_id']} | 턴: {s['turns']} | 목표: {s.get('goal', '-')}")
                else:
                    print(f"  {C_GRAY}활성 세션 없음{C_RESET}")
            except Exception as e:
                print(f"  {C_RED}상태 조회 실패: {e}{C_RESET}")
            continue
        elif cmd == ":help":
            print(f"""
  {C_CYAN}:quit{C_RESET}      종료
  {C_CYAN}:reset{C_RESET}     세션 초기화 (대화 히스토리 삭제)
  {C_CYAN}:dir PATH{C_RESET}  작업 디렉토리 변경
  {C_CYAN}:status{C_RESET}    에이전트 세션 상태 확인
  {C_CYAN}:help{C_RESET}      이 도움말
""")
            continue

        agent_ok = check_agent()

        if False and not agent_ok:
            # 에이전트 비활성 → 기본 채팅
            print(f"\n{C_YELLOW}(에이전트 비활성 — 기본 채팅 모드){C_RESET}")
            try:
                payload = {
                    "messages": [{"role": "user", "content": user_input}],
                    "max_tokens": 1024,
                    "temperature": 0.3,
                }
                r = requests.post(f"{SERVER}/chat", json=payload, timeout=300)
                r.raise_for_status()
                reply = r.json().get("response", "")
                print(f"\n{C_BLUE}[AI]{C_RESET}\n{reply}")
            except Exception as e:
                print(f"{C_RED}오류: {e}{C_RESET}")
            continue

        # 에이전트 모드 실행
        print(f"\n{C_YELLOW}에이전트 실행 중... (최대 15단계){C_RESET}")
        print(f"{C_GRAY}  작업 디렉토리: {working_dir}{C_RESET}")
        print()

        t0 = time.time()
        try:
            result = run_agent(user_input, session_id, working_dir)
            elapsed = (time.time() - t0)

            # 단계별 출력
            for step in result.get("steps", []):
                print_step(step)

            # 최종 답변
            answer = result.get("answer", "")
            server_ms = result.get("elapsed_ms", 0)

            print()
            print(f"{C_BLUE}{'─'*60}{C_RESET}")
            print(f"{C_BOLD}{C_BLUE}[에이전트 답변]{C_RESET}")
            print(answer)
            print(f"{C_BLUE}{'─'*60}{C_RESET}")
            print(f"{C_GRAY}  서버 처리: {server_ms/1000:.1f}초 | 총 경과: {elapsed:.1f}초{C_RESET}")

        except requests.exceptions.Timeout:
            print(f"{C_RED}시간 초과 (10분) — 요청이 너무 복잡할 수 있습니다.{C_RESET}")
        except Exception as e:
            print(f"{C_RED}오류: {e}{C_RESET}")


if __name__ == "__main__":
    main()
