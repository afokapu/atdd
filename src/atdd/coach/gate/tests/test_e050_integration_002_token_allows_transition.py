# URN: test:govern-lifecycle:operator-approval-token-gate:E050-INTEGRATION-002-operator-signed-token-allows-transition
# Acceptance: acc:govern-lifecycle:E050-INTEGRATION-002-operator-signed-token-allows-transition
# WMBT: wmbt:govern-lifecycle:E050
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""E050-INTEGRATION-002 — a valid operator-signed token lets the transition proceed.

With a correctly-signed token written for the exact (issue, PLANNED, RED) tuple
under the worktree, the ApprovalTokenGateCheck passes and transition() proceeds
to IssueManager.update().

RED state: there is no atdd.coach.gate.approval / approval_check module.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.gate.approval import approval_relpath, build_token
from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
from atdd.coach.gate.registry import GATE_REGISTRY
from atdd.coach.commands.issue_lifecycle import IssueLifecycle

pytestmark = [pytest.mark.platform]

_KEY = "operator-secret-key"


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


def test_valid_token_allows_transition(tmp_path: Path, planned_issue, clean_registry):
    """E050-INTEGRATION-002: a valid signed token in the worktree passes the gate."""
    token_path = tmp_path / approval_relpath(1017, "PLANNED", "RED")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(
        build_token(1017, "PLANNED", "RED", approved_by="alec", approved_at="t", key=_KEY)
    ))

    clean_registry.register("PLANNED", "RED", ApprovalTokenGateCheck(signing_key=_KEY))
    config = {"gate": {"transitions": {"PLANNED->RED": True}}}
    lifecycle = IssueLifecycle(target_dir=tmp_path)

    update_spy = MagicMock(return_value=0)
    with patch.object(IssueLifecycle, "_fetch_issue", return_value=planned_issue), \
         patch.object(IssueLifecycle, "_load_config", return_value=config), \
         patch.object(IssueLifecycle, "_compliance_gate", return_value=0), \
         patch.object(IssueLifecycle, "_reenter_display_only", return_value=0), \
         patch("atdd.coach.commands.issue.IssueManager.update", update_spy):
        rc = lifecycle.transition(1017, "RED", force=False)

    assert rc == 0
    assert update_spy.called, (
        "a valid operator token must let the transition proceed to IssueManager.update()"
    )
