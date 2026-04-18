"""P6-1: E2E 회귀 검증 스크립트 — Agent WinForm 시나리오

실행 방법:
    python tests/e2e_agent_winform.py [--url http://localhost:8888] [--context-dir D:\\some\\dir]

검증 항목:
    1. 서버 healthcheck (/health) 응답 확인
    2. /agent/stream POST:
         prompt  = "C# 으로 Winform 프로그램 만듭시다"
         kind    구분 가능 여부 (agent 호출이 대시보드에 기록되는지)
    3. 첫 토큰(또는 첫 step) 수신까지 60s 이내
    4. action=="answer" 도달 또는 total 5분 이내 완료
    5. /stats 에서 kind 가 "agent" 또는 "agent-step" 인 항목이 1개 이상 포함되는지 확인

종료 코드:
    0 — 모든 검증 통과
    1 — 검증 실패 (stderr 에 사유 출력)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import tempfile
import os

try:
    import requests
except ImportError:
    print("FAIL: 'requests' 패키지가 필요합니다. pip install requests", file=sys.stderr)
    sys.exit(1)

# ---- 설정 상수 ---------------------------------------------------------------
DEFAULT_URL = "http://localhost:8888"
PROMPT = "C# 으로 Winform 프로그램 만듭시다"
FIRST_TOKEN_TIMEOUT_S = 60      # 첫 step/토큰 수신 기한 (초)
TOTAL_TIMEOUT_S = 300           # 전체 완료 기한 (초, = 5분)
HEALTH_TIMEOUT_S = 10           # /health 응답 기한 (초)
# -----------------------------------------------------------------------------


def _fmt_elapsed(s: float) -> str:
    return f"{s:.1f}s"


def step_check(condition: bool, label: str, detail: str = ""):
    prefix = "PASS" if condition else "FAIL"
    msg = f"[{prefix}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg, file=sys.stderr if not condition else sys.stdout)
    return condition


def check_health(base_url: str) -> bool:
    """Step 1: /health 응답 확인."""
    try:
        r = requests.get(f"{base_url}/health", timeout=HEALTH_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        status = data.get("status", "")
        model = data.get("model", "")
        return step_check(
            status == "ok",
            "healthcheck /health",
            f"status={status!r}, model={model!r}",
        )
    except requests.exceptions.ConnectionError:
        return step_check(False, "healthcheck /health", f"ConnectionError — 서버가 {base_url} 에서 실행 중인지 확인하세요.")
    except requests.exceptions.Timeout:
        return step_check(False, "healthcheck /health", f"Timeout ({HEALTH_TIMEOUT_S}s)")
    except Exception as e:
        return step_check(False, "healthcheck /health", f"{type(e).__name__}: {e}")


def check_agent_stream(base_url: str, context_dir: str) -> tuple[bool, bool, bool]:
    """Step 2–4: /agent/stream 스트리밍 검증.

    반환: (first_token_ok, answer_reached_ok, no_error_ok)
    """
    url = f"{base_url}/agent/stream"
    payload = {
        "message": PROMPT,
        "session_id": "e2e_winform",
        "working_dir": context_dir,
        "max_iterations": 10,
        "temperature": 0.1,
        "max_tokens": 512,
    }

    first_step_time: float | None = None
    answer_reached = False
    last_error: str | None = None
    step_count = 0
    warn_large_prompt = False

    t_start = time.monotonic()

    try:
        with requests.post(url, json=payload, stream=True, timeout=(15, None)) as resp:
            resp.raise_for_status()

            for raw_line in resp.iter_lines(decode_unicode=True):
                now = time.monotonic()
                elapsed = now - t_start

                # 전체 타임아웃
                if elapsed > TOTAL_TIMEOUT_S:
                    print(
                        f"  [timeout] 전체 {TOTAL_TIMEOUT_S}s 초과, 현재까지 step={step_count}",
                        file=sys.stderr,
                    )
                    break

                if not raw_line:
                    continue

                try:
                    evt = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                evt_type = evt.get("type", "")

                # heartbeat — 살아있다는 신호만
                if evt_type == "heartbeat":
                    continue

                # 첫 의미있는 이벤트 기록
                if first_step_time is None:
                    first_step_time = elapsed
                    print(f"  [info] 첫 이벤트 수신: {_fmt_elapsed(elapsed)}, type={evt_type!r}")

                step_count += 1

                if evt_type == "step":
                    inner = evt.get("step", {})
                    inner_type = inner.get("type", "")
                    inner_kind = inner.get("kind", "")

                    # P6-2 경고 step 감지
                    if inner_kind == "warn" and inner.get("msg") == "prompt too large":
                        warn_large_prompt = True
                        est = inner.get("estimated_tokens", "?")
                        print(f"  [warn] prompt too large 경고 수신 (estimated_tokens={est})")

                    if inner_type == "action":
                        action = inner.get("action", "")
                        thought = inner.get("thought", "")[:80]
                        print(f"  [step] iteration={inner.get('iteration','?')} action={action!r} thought={thought!r}")
                        if action == "answer":
                            answer_reached = True
                            print(f"  [info] action==answer 도달, elapsed={_fmt_elapsed(elapsed)}")
                            break

                elif evt_type == "final":
                    answer_text = evt.get("answer", "")
                    elapsed_ms = evt.get("elapsed_ms", 0)
                    print(f"  [final] elapsed_ms={elapsed_ms}, answer_len={len(answer_text)}")
                    answer_reached = True
                    break

                elif evt_type == "error":
                    last_error = evt.get("error", "unknown")
                    print(f"  [error] {last_error}", file=sys.stderr)
                    break

    except requests.exceptions.ConnectionError as e:
        return (
            step_check(False, "첫 step 수신 60s 이내", f"ConnectionError: {e}"),
            False,
            False,
        )
    except requests.exceptions.Timeout as e:
        return (
            step_check(False, "첫 step 수신 60s 이내", f"Timeout: {e}"),
            False,
            False,
        )
    except Exception as e:
        return (
            step_check(False, "첫 step 수신 60s 이내", f"{type(e).__name__}: {e}"),
            False,
            False,
        )

    total_elapsed = time.monotonic() - t_start

    # 검증 1: 첫 토큰/step 60s 이내
    ok_first = first_step_time is not None and first_step_time <= FIRST_TOKEN_TIMEOUT_S
    step_check(
        ok_first,
        f"첫 step 수신 {FIRST_TOKEN_TIMEOUT_S}s 이내",
        f"first_step_time={_fmt_elapsed(first_step_time) if first_step_time is not None else 'None'}",
    )

    # 검증 2: answer 도달 or 5분 이내 완료
    ok_total = total_elapsed <= TOTAL_TIMEOUT_S
    step_check(
        ok_total,
        f"전체 완료 {TOTAL_TIMEOUT_S}s 이내",
        f"elapsed={_fmt_elapsed(total_elapsed)}",
    )

    # 검증 3: answer action 도달
    step_check(
        answer_reached,
        'action=="answer" 도달',
        f"steps processed={step_count}, last_error={last_error!r}",
    )

    # 참고 출력 (실패 기준 아님)
    if warn_large_prompt:
        print("  [info] P6-2 토큰 경고가 발행되었습니다 (정상 동작).")
    else:
        print("  [info] P6-2 토큰 경고 없음 (prompt 크기가 임계 미만이거나 경고 로직 미동작).")

    return ok_first, ok_total, answer_reached


def check_stats_kind(base_url: str) -> bool:
    """Step 5: /stats 에서 kind='agent' 또는 'agent-step' 항목 확인 (P6-3 검증)."""
    try:
        r = requests.get(f"{base_url}/stats", timeout=10)
        r.raise_for_status()
        data = r.json()
        recent = data.get("recent", [])
        agent_entries = [x for x in recent if x.get("kind", "chat") in ("agent", "agent-step")]
        ok = len(agent_entries) > 0
        detail = f"recent={len(recent)}건 중 agent/agent-step={len(agent_entries)}건"
        return step_check(ok, "P6-3 /stats kind 컬럼 agent 항목 존재", detail)
    except Exception as e:
        return step_check(False, "P6-3 /stats kind 컬럼 확인", f"{type(e).__name__}: {e}")


def main():
    parser = argparse.ArgumentParser(description="E2E Agent WinForm 회귀 검증")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"서버 base URL (기본: {DEFAULT_URL})")
    parser.add_argument(
        "--context-dir",
        default=None,
        help="에이전트 working_dir 로 지정할 폴더 경로. 미지정 시 임시 디렉토리 사용.",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    # context_dir 결정
    if args.context_dir:
        context_dir = args.context_dir
        if not os.path.isdir(context_dir):
            print(f"FAIL: --context-dir '{context_dir}' 가 존재하지 않습니다.", file=sys.stderr)
            sys.exit(1)
        _tmp_dir_obj = None
    else:
        _tmp_dir_obj = tempfile.TemporaryDirectory(prefix="e2e_winform_")
        context_dir = _tmp_dir_obj.name

    print("=" * 60)
    print(f"Sm_AICoder E2E 회귀 검증 — Agent WinForm 시나리오")
    print(f"  서버  : {base_url}")
    print(f"  prompt: {PROMPT!r}")
    print(f"  dir   : {context_dir}")
    print("=" * 60)

    results: list[bool] = []

    # Step 1: healthcheck
    print("\n[1/5] Healthcheck")
    results.append(check_health(base_url))
    if not results[-1]:
        print("\n서버가 응답하지 않습니다. 나머지 검증을 건너뜁니다.", file=sys.stderr)
        sys.exit(1)

    # Step 2-4: agent/stream
    print(f"\n[2-4/5] /agent/stream POST (timeout first={FIRST_TOKEN_TIMEOUT_S}s, total={TOTAL_TIMEOUT_S}s)")
    ok_first, ok_total, ok_answer = check_agent_stream(base_url, context_dir)
    results += [ok_first, ok_total, ok_answer]

    # Step 5: /stats kind 컬럼
    print("\n[5/5] /stats kind 컬럼 확인 (P6-3)")
    results.append(check_stats_kind(base_url))

    # 정리
    if _tmp_dir_obj is not None:
        try:
            _tmp_dir_obj.cleanup()
        except Exception:
            pass

    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"결과: {passed}/{total} 통과")
    print("=" * 60)

    if passed == total:
        print("ALL PASS")
        sys.exit(0)
    else:
        failed = [i + 1 for i, r in enumerate(results) if not r]
        print(f"FAIL (항목 {failed})", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
