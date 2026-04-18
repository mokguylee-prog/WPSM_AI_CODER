#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


DEFAULT_STATUS = {
    "server_resilience": {
        "single_session_failure_isolated": False,
        "retry_timeout_health_cleanup": False,
        "session_work_connection_separated": False,
    },
    "client_feedback": {
        "success_failure_in_progress_clear": False,
        "failure_reason_visible": False,
    },
    "reconnect_stability": {
        "reconnect_does_not_mix_sessions": False,
        "reconnect_does_not_fake_offline": False,
    },
    "observability": {
        "health_stable": False,
        "secondary_failures_do_not_mean_offline": False,
        "logs_are_useful": False,
    },
    "recovery_workflow": {
        "next_action_guided": False,
        "auto_vs_manual_clear": False,
        "repro_driven_fixing": False,
    },
}

WEIGHTS = {
    "server_resilience": 30,
    "client_feedback": 20,
    "reconnect_stability": 20,
    "observability": 15,
    "recovery_workflow": 15,
}


def load_status(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return DEFAULT_STATUS


def score_section(entries: dict, points: int) -> tuple[int, list[str]]:
    keys = list(entries.keys())
    earned = sum(1 for v in entries.values() if bool(v))
    section_score = round(points * earned / max(1, len(keys)))
    missing = [k for k, v in entries.items() if not bool(v)]
    return section_score, missing


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    status = load_status(root / "QUALITY_STATUS.json")

    total = 0
    report = []
    for section, points in WEIGHTS.items():
        section_score, missing = score_section(status.get(section, {}), points)
        total += section_score
        report.append((section, section_score, missing))

    print(f"Total Score: {total}/100")
    for section, section_score, missing in report:
        print(f"- {section}: {section_score}")
        if missing:
            print(f"  missing: {', '.join(missing)}")

    if total < 90:
        print("Gate: FAIL")
        return 1

    print("Gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
