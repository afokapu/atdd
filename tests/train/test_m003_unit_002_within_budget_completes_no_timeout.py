# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:M003-UNIT-002-within-budget-completes-no-timeout
# Acceptance: acc:spawn-agents:M003-UNIT-002-within-budget-completes-no-timeout
# WMBT: wmbt:spawn-agents:M003
# Phase: GREEN
# Layer: backend.application
# Assertion: behavioral
"""M003-UNIT-002 — a warm-resume that completes within budget proceeds normally
and fires no timeout (no false positives on the happy path).

RED: fails until ``run_warm_resume_with_timeout`` returns the action's result
and never escalates when the action finishes under budget.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.coder]


def test_within_budget_returns_result_and_no_escalation():
    from atdd.train.warm_resume_watchdog import run_warm_resume_with_timeout

    escalations: list[dict] = []

    def quick_action():
        return {"advanced": True}

    outcome = run_warm_resume_with_timeout(
        quick_action,
        issue_number=1079,
        transition="PLANNED->RED",
        budget_s=5.0,
        on_timeout=escalations.append,
    )

    assert getattr(outcome, "status", None) == "completed"
    assert getattr(outcome, "result", None) == {"advanced": True}
    assert escalations == [], "no timeout escalation on the happy path"
