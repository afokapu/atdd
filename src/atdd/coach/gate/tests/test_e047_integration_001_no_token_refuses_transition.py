# URN: test:govern-lifecycle:operator-approval-token-gate:E047-INTEGRATION-001-no-token-refuses-transition-label-unchanged
# Acceptance: acc:govern-lifecycle:E047-INTEGRATION-001-no-token-refuses-transition-label-unchanged
# WMBT: wmbt:govern-lifecycle:E047
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""E047-INTEGRATION-001 — no operator token => transition refused, label unchanged.

Anti-theater (mirrors #1020 E045): the ApprovalTokenGateCheck registered for
PLANNED->RED must REFUSE the worker's transition when no operator-signed token
exists — non-zero exit AND IssueManager.update() (the label/phase swap) never
reached. We prove "did not occur" behaviorally via a recording fake on update(),
not by scraping a printed line.

RED state: there is no atdd.coach.gate.approval_check module to register.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
from atdd.coach.gate.registry import GATE_REGISTRY
from atdd.coach.commands.issue_lifecycle import IssueLifecycle

pytestmark = [pytest.mark.platform]


@pytest.fixture
def planned_issue():
    return {
        "number": 1017,
        "title": "Daemon operator-reserved decision gate",
        "state": "OPEN",
        "labels": [{"name": "atdd-issue"}, {"name": "atdd:PLANNED"}],
        "body": "",
    }


@pytest.fixture
def clean_registry():
    before = GATE_REGISTRY.checks_for("PLANNED", "RED")
    yield GATE_REGISTRY
    GATE_REGISTRY.clear("PLANNED", "RED")
    for chk in before:
        GATE_REGISTRY.register("PLANNED", "RED", chk)


def test_no_token_refuses_transition_label_unchanged(tmp_path: Path, planned_issue, clean_registry):
    """E047-INTEGRATION-001: a missing approval token blocks PLANNED->RED."""
    clean_registry.register("PLANNED", "RED", ApprovalTokenGateCheck(signing_key="k"))

    # Operator-gated transition must be enabled for this transition.
    config = {"gate": {"transitions": {"PLANNED->RED": True}}}
    lifecycle = IssueLifecycle(target_dir=tmp_path)

    update_spy = MagicMock(return_value=0)
    with patch.object(IssueLifecycle, "_fetch_issue", return_value=planned_issue), \
         patch.object(IssueLifecycle, "_load_config", return_value=config), \
         patch("atdd.coach.commands.issue.IssueManager.update", update_spy):
        rc = lifecycle.transition(1017, "RED", force=False)

    assert rc != 0, "a missing approval token must make the transition return non-zero"
    assert not update_spy.called, (
        "the transition occurred despite no operator approval token — "
        "IssueManager.update() (the label/phase swap) must never be reached"
    )
