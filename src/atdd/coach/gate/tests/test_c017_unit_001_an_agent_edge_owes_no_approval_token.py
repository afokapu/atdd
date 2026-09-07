# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C017-UNIT-001-an-agent-edge-owes-no-approval-token
# Acceptance: acc:govern-lifecycle:C017-UNIT-001-an-agent-edge-owes-no-approval-token
# WMBT: wmbt:govern-lifecycle:C017
# Phase: RED
# Layer: application
"""C017-UNIT-001 — an edge the machine calls agent-submittable owes no token.

`gate.transitions` gates an EDGE, but two checks of different kinds ride on
SMOKE->REFACTOR: the #1602 evidence check the edge was listed to enable, and this
approval check, which attached as collateral. The machine already declares who
may submit; the check must read it.
"""
from __future__ import annotations

from pathlib import Path

from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
from atdd.coach.gate.decision import GateContext, GateVerdict


def _ctx(tmp_path: Path, from_phase: str, to_phase: str) -> GateContext:
    return GateContext(
        issue_number=4242, from_phase=from_phase, to_phase=to_phase, worktree=tmp_path
    )


def test_agent_edge_owes_no_token(tmp_path):
    # No token is written anywhere: the point is that none is owed.
    result = ApprovalTokenGateCheck().run(_ctx(tmp_path, "SMOKE", "REFACTOR"))

    assert result.verdict == GateVerdict.NOT_APPLICABLE, (
        "SMOKE->REFACTOR is declared `autonomy: agent`, so no operator token is "
        f"owed; got {result.verdict} — {result.message}"
    )
    assert "agent" in result.message.lower(), (
        "the message must name the declared autonomy so the verdict is "
        f"attributable to the convention, not to this check: {result.message!r}"
    )


def test_operator_edge_with_no_token_still_fails(tmp_path):
    # The guard against over-reach: this change must remove no existing refusal.
    result = ApprovalTokenGateCheck().run(_ctx(tmp_path, "PLANNED", "RED"))

    assert result.verdict == GateVerdict.FAIL, (
        "PLANNED->RED is declared `autonomy: operator` and has no token, so it "
        f"must still refuse; got {result.verdict} — {result.message}"
    )
