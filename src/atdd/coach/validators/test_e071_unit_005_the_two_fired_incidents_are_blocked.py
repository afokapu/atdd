# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E071-UNIT-005-the-two-fired-incidents-are-blocked
# Acceptance: acc:govern-lifecycle:E071-UNIT-005-the-two-fired-incidents-are-blocked
# WMBT: wmbt:govern-lifecycle:E071
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E071-UNIT-005 — the two merges that already fired the incident must read BLOCKED.

This is not a hypothetical the gate should have caught. It fired twice on
2026-08-03, hours apart, and both auto-closes landed one second after the merge:

    PR #1648  merged 2026-08-03T01:05:22Z  →  #1635 closed 01:05:23Z  (+1s)
    PR #1691  merged 2026-08-03T03:36:28Z  →  #1689 closed 03:36:29Z  (+1s)

Both issues closed with ``stateReason: COMPLETED``. Both still carry
``atdd:SMOKE``: neither ever reached REFACTOR or COMPLETE, so the operator
sign-off REFACTOR exists to require (``autonomy: operator``, #1611) was skipped
in both. #1635 is a program umbrella and was closed with 8 of its 10 children
still open — the auto-close does not ask whether the work is done.

The fixtures below are the resolutions ``PRManager.resolve_linked_issue``
actually returned for those two PRs, read from the live API, not invented. The
strategy is ``api`` in both — the ``closingIssuesReferences`` field, which is
the mechanism GitHub itself acted on, so this is the gate being shown the exact
input that produced the incident.

A synthetic SMOKE case (E071-UNIT-001) shows the rule is right. This shows it
would have stopped what actually happened.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as mod

_RULE_ID = "coach.pr.merge-blocks-on-pre-smoke-close"

#: Measured 2026-08-03 via the real PRManager against the live GitHub API.
FIRED_INCIDENTS = [
    {"pr_number": 1648, "issue_number": 1635, "phase_label": "SMOKE", "strategy": "api"},
    {"pr_number": 1691, "issue_number": 1689, "phase_label": "SMOKE", "strategy": "api"},
]


@pytest.mark.parametrize(
    "incident", FIRED_INCIDENTS, ids=lambda i: f"PR{i['pr_number']}-issue{i['issue_number']}"
)
def test_the_gate_reports_blocked_for_a_merge_that_already_fired(incident: dict) -> None:
    violations = mod.evaluate_pr_merge_violations([incident])

    assert len(violations) == 1, (
        f"PR #{incident['pr_number']} merged and closed issue "
        f"#{incident['issue_number']} at atdd:SMOKE one second later. The gate must "
        f"report BLOCKED for it. Got {violations!r}"
    )
    violation = violations[0]
    assert violation.rule_id == _RULE_ID
    assert violation.location == f"PR#{incident['pr_number']}:0"
    assert str(incident["issue_number"]) in violation.detail
    assert "atdd:SMOKE" in violation.detail


def test_both_incidents_block_when_judged_together() -> None:
    """One evaluation, both offenders — a fix that catches one shape is not a fix."""
    violations = mod.evaluate_pr_merge_violations(FIRED_INCIDENTS)
    assert {v.location for v in violations} == {"PR#1648:0", "PR#1691:0"}
