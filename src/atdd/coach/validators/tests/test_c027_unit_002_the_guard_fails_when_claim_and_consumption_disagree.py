# URN: test:govern-lifecycle:define-transition-autonomy:C027-UNIT-002-the-guard-fails-when-claim-and-consumption-disagree
# Acceptance: acc:govern-lifecycle:C027-UNIT-002-the-guard-fails-when-claim-and-consumption-disagree
# WMBT: wmbt:govern-lifecycle:C027
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C027-UNIT-002 — the guard catches the drift whichever side moves.

#1798 moved the runtime and left the prose. The symmetric failure is equally
possible: a later issue removes the waiver and leaves a node advertising a reader
that no longer exists. Both are one defect — a declaration that does not describe
the system — so both must fail, and the message must say WHICH side moved, because
the two have opposite remedies.

Driven with fabricated nodes and a stub check, so the acceptance does not depend
on the repository's own current state. C027-SMOKE-001 is where the committed pair
is asserted.
"""
from __future__ import annotations

import pytest

from ._c027_autonomy_claim import resolve_claim

from atdd.coach.gate.decision import GateCheckResult, GateContext

pytestmark = [pytest.mark.coach, pytest.mark.platform]

_GATE_ID = "approval-token"
_RULE_ID = "govern-lifecycle.E050.operator-approval-required"

CLAIMS_INERT = {
    "statement": "ATDD retains sole authority, so a permissive declaration can at "
                 "worst submit a command ATDD then rejects.",
    "metadata": {"disposition": "documentation-only"},
}
CLAIMS_READ = {
    "statement": "The approval gate reads this key: ApprovalTokenGateCheck waives "
                 "the operator token on a phase declaring `autonomy: agent`.",
    "metadata": {"disposition": "enforced"},
}


class _ReadsAutonomy:
    """A check whose verdict turns on the declared autonomy, as #1798's does."""

    gate_id = _GATE_ID

    def run(self, ctx: GateContext) -> GateCheckResult:
        if ctx.from_phase.upper() == "SMOKE":
            return GateCheckResult.not_applicable(
                _GATE_ID, _RULE_ID, "declares `autonomy: agent`",
            )
        return GateCheckResult(_GATE_ID, _RULE_ID, False, "no token")


class _IgnoresAutonomy:
    """A check that demands a token regardless of what the machine declares."""

    gate_id = _GATE_ID

    def run(self, ctx: GateContext) -> GateCheckResult:
        return GateCheckResult(_GATE_ID, _RULE_ID, False, "no token")


@pytest.mark.platform
def test_runtime_moved_is_caught() -> None:
    """A node claiming inertness beside a gate that reads the key FAILS."""
    verdict = resolve_claim(CLAIMS_INERT, _ReadsAutonomy())
    assert not verdict, "the #1798 drift itself was not caught"
    assert "RUNTIME MOVED" in verdict.detail, (
        f"the failure must name which side moved; got {verdict.detail!r}"
    )


@pytest.mark.platform
def test_node_moved_is_caught() -> None:
    """A node advertising a reader beside a gate that ignores the key FAILS."""
    verdict = resolve_claim(CLAIMS_READ, _IgnoresAutonomy())
    assert not verdict, (
        "the symmetric drift was not caught — a guard that only watches the prose "
        "would pass a repo whose waiver had been silently removed"
    )
    assert "NODE MOVED" in verdict.detail, (
        f"the failure must name which side moved; got {verdict.detail!r}"
    )


@pytest.mark.platform
@pytest.mark.parametrize(
    "node,check",
    [(CLAIMS_READ, _ReadsAutonomy()), (CLAIMS_INERT, _IgnoresAutonomy())],
    ids=["both-say-read", "both-say-inert"],
)
def test_agreement_passes(node, check) -> None:
    """The guard is not an unconditional refusal — agreement in either regime passes."""
    verdict = resolve_claim(node, check)
    assert verdict, (
        f"the guard refused a consistent pair, which would make it unfixable: "
        f"{verdict.detail!r}"
    )
