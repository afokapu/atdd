# URN: test:govern-lifecycle:enforcing-phase-transition-gate:E045-INTEGRATION-001-failing-check-refuses-transition-label-unchanged
# Acceptance: acc:govern-lifecycle:E045-INTEGRATION-001-failing-check-refuses-transition-label-unchanged
# Acceptance: acc:govern-lifecycle:E045-INTEGRATION-002-passing-check-allows-transition
# WMBT: wmbt:govern-lifecycle:E045
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""E045 — the enforcing gate acts on its verdict in IssueLifecycle.transition().

Anti-theater (the #865 lesson applied to the gate itself): a registered FAILING
gate check must REFUSE the transition — non-zero exit AND the transition does not
occur. We prove "did not occur" behaviorally by asserting IssueManager.update()
(the call that swaps the GitHub label / advances the phase) was NEVER reached —
not by scraping a 'gate failed' log line. A registered PASSING check lets the
transition proceed to update().

RED state: IssueLifecycle.transition() does not consult any per-transition gate
registry, so a failing check cannot block — update() runs regardless.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.gate.decision import GateCheckResult
from atdd.coach.gate.registry import GATE_REGISTRY
from atdd.coach.commands.issue_lifecycle import IssueLifecycle

pytestmark = [pytest.mark.platform]


@dataclass
class _FakeCheck:
    """A registerable GateCheck whose verdict is fixed for the test."""

    gate_id: str
    rule_id: str
    verdict_passed: bool

    def run(self, ctx) -> GateCheckResult:
        return GateCheckResult(
            gate_id=self.gate_id,
            rule_id=self.rule_id,
            passed=self.verdict_passed,
            message="fake check verdict",
        )


@pytest.fixture
def planned_issue():
    """A fake issue currently labelled atdd:PLANNED (so from_phase=PLANNED)."""
    return {
        "number": 1020,
        "title": "Enforcing gate keystone",
        "state": "OPEN",
        "labels": [{"name": "atdd-issue"}, {"name": "atdd:PLANNED"}],
        "body": "",
    }


@pytest.fixture
def clean_registry():
    """Register checks into the live GATE_REGISTRY and tear them down."""
    before = GATE_REGISTRY.checks_for("PLANNED", "RED")
    yield GATE_REGISTRY
    # Restore: clear anything we added for PLANNED->RED
    GATE_REGISTRY.clear("PLANNED", "RED")
    for chk in before:
        GATE_REGISTRY.register("PLANNED", "RED", chk)


def test_failing_check_refuses_transition_label_unchanged(
    tmp_path: Path, planned_issue, clean_registry
):
    """E045-INTEGRATION-001: a failing registered check blocks the transition.

    Non-zero exit AND IssueManager.update() never called (transition did not
    occur — no label swap, no phase advance).
    """
    clean_registry.register(
        "PLANNED", "RED",
        _FakeCheck("GT-TEST-FAIL", "repo.govern-lifecycle.E045-fail", verdict_passed=False),
    )

    lifecycle = IssueLifecycle(target_dir=tmp_path)

    update_spy = MagicMock(return_value=0)
    with patch.object(IssueLifecycle, "_fetch_issue", return_value=planned_issue), \
         patch("atdd.coach.commands.issue.IssueManager.update", update_spy):
        rc = lifecycle.transition(1020, "RED", force=False)

    assert rc != 0, "a failing gate check must make the transition return non-zero"
    assert not update_spy.called, (
        "the transition occurred despite a failing gate check — "
        "IssueManager.update() (the label/phase swap) must never be reached"
    )


def test_passing_check_allows_transition(tmp_path: Path, planned_issue, clean_registry):
    """E045-INTEGRATION-002: a passing registered check lets the transition proceed."""
    clean_registry.register(
        "PLANNED", "RED",
        _FakeCheck("GT-TEST-PASS", "repo.govern-lifecycle.E045-pass", verdict_passed=True),
    )

    lifecycle = IssueLifecycle(target_dir=tmp_path)

    update_spy = MagicMock(return_value=0)
    with patch.object(IssueLifecycle, "_fetch_issue", return_value=planned_issue), \
         patch.object(IssueLifecycle, "_compliance_gate", return_value=0), \
         patch.object(IssueLifecycle, "_reenter_display_only", return_value=0), \
         patch("atdd.coach.commands.issue.IssueManager.update", update_spy):
        rc = lifecycle.transition(1020, "RED", force=False)

    assert rc == 0
    assert update_spy.called, (
        "a passing gate check must let the transition proceed to IssueManager.update()"
    )
