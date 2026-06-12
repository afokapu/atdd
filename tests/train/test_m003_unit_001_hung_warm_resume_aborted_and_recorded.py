# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:M003-UNIT-001-hung-warm-resume-aborted-and-recorded
# Acceptance: acc:spawn-agents:M003-UNIT-001-hung-warm-resume-aborted-and-recorded
# WMBT: wmbt:spawn-agents:M003
# Phase: GREEN
# Layer: backend.application
# Assertion: behavioral
"""M003-UNIT-001 — a warm-resume that exceeds the timeout budget is aborted at the
budget and recorded (never an unbounded block).

RED: fails until ``run_warm_resume_with_timeout`` exists in
``atdd.train.warm_resume_watchdog`` and bounds + escalates a hung action.
"""
from __future__ import annotations

import threading
import time

import pytest

pytestmark = [pytest.mark.coder]


def test_hung_action_returns_within_budget_and_escalates():
    from atdd.train.warm_resume_watchdog import run_warm_resume_with_timeout

    release = threading.Event()
    escalations: list[dict] = []

    def hung_action():
        # Blocks far longer than the budget; released only on cleanup.
        release.wait(5.0)
        return "should-not-be-used"

    started = time.monotonic()
    try:
        outcome = run_warm_resume_with_timeout(
            hung_action,
            issue_number=1079,
            transition="RED->GREEN",
            budget_s=0.3,
            on_timeout=escalations.append,
        )
    finally:
        release.set()
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, f"watchdog must return near the budget, not block: {elapsed:.2f}s"
    assert getattr(outcome, "status", None) == "timed_out"
    assert len(escalations) == 1, "exactly one timeout escalation recorded"
    record = escalations[0]
    assert record.get("issue_number") == 1079
    assert record.get("transition") == "RED->GREEN"
    assert "elapsed_s" in record, "the escalation must record elapsed time"
