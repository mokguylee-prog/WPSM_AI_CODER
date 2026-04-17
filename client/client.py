"""Sm_AICoder 대화형 클라이언트 — 자연어로 코드를 요청합니다."""
import requests
import json
import sys
import os

SERVER = "http://localhost:8888"
HISTORY: list[dict] = []  # 대화 히스토리 (다중 턴 유지)


def check_server() -> str:
    try:
        r = requests.get(f"{SERVER}/health", timeout=5)
        r.raise_for_status()
        return r.json().get("model", "unknown")
    except Exception as e:
        print(f"서버에 연결할 수 없습니다: {e}")
        print("start_server.ps1 로 서버를 먼저 시작하세요.")
        sys.exit(1)


def ask(prompt: str, max_tokens: int = 1024, temperature: float = 0.3) -> str:
    HISTORY.append({"role": "user", "content": prompt})

    payload = {
        "messages": HISTORY,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    r = requests.post(f"{SERVER}/chat", json=payload, timeout=300)
    r.raise_for_status()
    data = r.json()

    reply = data["message"]["content"]
    HISTORY.append({"role": "assistant", "content": reply})
    tokens = data.get("usage", {})
    return reply, tokens


def print_help():
    print("""
명령어:
  :clear    대화 히스토리 초기화 (새 대화 시작)
  :temp N   생성 온도 변경 (0.0~1.0, 낮을수록 확정적)
  :tokens N 최대 생성 토큰 수 변경
  :save     마지막 응답을 output.txt에 저장
  :quit     종료 (또는 Ctrl+C)
  :help     이 도움말
""")


def print_banner(model: str):
    w = 50
    print("╔" + "═" * w + "╗")
    print(f"║  Sm_AICoder Instruction-Following 코드 생성기   ║")
    print(f"║  모델: {model[:w-8]:<{w-8}}  ║")
    print("╠" + "═" * w + "╣")
    print("║  자연어로 코드를 요청하세요                    ║")
    print("║  여러 줄 입력 → 빈 줄로 전송                  ║")
    print("║  :help 로 명령어 확인                          ║")
    print("╚" + "═" * w + "╝")
    print()


def collect_input(prompt_str: str) -> str:
    lines = []
    print(prompt_str, end="", flush=True)
    while True:
        line = input()
        if line == "" and lines:
            break
        if line == "" and not lines:
            continue
        lines.append(line)
    return "\n".join(lines)


def main():
    model = check_server()
    print_banner(model)

    max_tokens = 1024
    temperature = 0.3
    last_reply = ""

    while True:
        try:
            user_input = collect_input("\n[YOU] >>> ")
        except (KeyboardInterrupt, EOFError):
            print("\n종료합니다.")
            break

        cmd = user_input.strip().lower()

        if cmd == ":quit":
            print("종료합니다.")
            break
        elif cmd == ":help":
            print_help()
            continue
        elif cmd == ":clear":
            HISTORY.clear()
            print("히스토리를 초기화했습니다.")
            continue
        elif cmd == ":save":
            with open("output.txt", "w", encoding="utf-8") as f:
                f.write(last_reply)
            print("output.txt 에 저장했습니다.")
            continue
        elif cmd.startswith(":temp "):
            try:
                temperature = float(cmd.split()[1])
                print(f"온도: {temperature}")
            except ValueError:
                print("사용법: :temp 0.3")
            continue
        elif cmd.startswith(":tokens "):
            try:
                max_tokens = int(cmd.split()[1])
                print(f"최대 토큰: {max_tokens}")
            except ValueError:
                print("사용법: :tokens 1024")
            continue

        print("\n생성 중...\n")
        try:
            reply, usage = ask(user_input, max_tokens=max_tokens, temperature=temperature)
            last_reply = reply
            print("─" * 60)
            print(reply)
            print("─" * 60)
            pt = usage.get("prompt_tokens", "?")
            ct = usage.get("completion_tokens", "?")
            print(f"[프롬프트 토큰: {pt} | 생성 토큰: {ct}]")
        except requests.exceptions.Timeout:
            print("시간 초과 — max_tokens를 줄이거나 서버를 확인하세요.")
        except Exception as e:
            print(f"오류: {e}")


if __name__ == "__main__":
    main()
