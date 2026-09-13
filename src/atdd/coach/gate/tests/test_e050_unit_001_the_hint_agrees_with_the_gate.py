# Acceptance: acc:drive-state-machine:D001-UNIT-001-hint-agrees-with-enforcement
"""GT-001 — `approval_required_for` must agree with `ApprovalTokenGateCheck` (#1999).

`approval_required_for` is the ONLY thing that tells an operator to approve an edge, and
its docstring says it asks two questions "and of nothing else": is the edge a candidate,
and does `.atdd/config.yaml` gate it. `autonomy` became a third input in #1798 —
`ApprovalTokenGateCheck._autonomy_waiver` returns NOT_APPLICABLE on an exact `agent` — and
the hint was never taught to ask it.

The measured consequence is 225 approval tokens on the operator's machine, of which
**95 are `SMOKE->REFACTOR`**: the hint prescribes that edge, the operator signs, and the
check waives the token without ever consulting it. The hint is the sole producer of all 95.

This is not a style complaint about a docstring. The two functions answer the same question
for the same operator and currently disagree on a live edge, so one of them is lying every
time an issue reaches SMOKE.

Convention: src/atdd/coach/conventions/nodes/coach.lifecycle.transition-autonomy.convention.yaml
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
from atdd.coach.gate.decision import GateContext, GateVerdict, is_transition_gated
from atdd.coach.gate.registrations import _CANDIDATE_TRANSITIONS, approval_required_for

pytestmark = [pytest.mark.coach]


#: The repo config as it stands: both edges gated, for two different reasons.
_REPO_CONFIG = {"gate": {"transitions": {"PLANNED->RED": True, "SMOKE->REFACTOR": True}}}


def _check_would_demand_a_token(from_phase: str, to_phase: str, tmp_path: Path) -> bool:
    """Whether the CHECK refuses this edge with no token present.

    NOT_APPLICABLE means the machine handed the edge to the persona and no human is owed
    anything. Anything else means the operator is genuinely on the hook.
    """
    result = ApprovalTokenGateCheck().run(
        GateContext(
            issue_number=1999,
            from_phase=from_phase,
            to_phase=to_phase,
            worktree=tmp_path,
        )
    )
    return result.verdict is not GateVerdict.NOT_APPLICABLE


@pytest.mark.parametrize(("from_phase", "to_phase"), _CANDIDATE_TRANSITIONS)
def test_the_hint_and_the_check_agree_on_every_candidate_edge(
    from_phase: str, to_phase: str, tmp_path: Path
) -> None:
    """What the operator is TOLD to sign is what the gate would actually demand."""
    told_to_sign = approval_required_for(_REPO_CONFIG, from_phase, to_phase)
    # An UNGATED edge consults no check at all — `evaluate_transition_gate` returns
    # proceed before the registry is read — so the honest comparison is against what
    # the gate would actually do, not against the check's verdict in isolation.
    actually_demanded = is_transition_gated(
        _REPO_CONFIG, from_phase, to_phase
    ) and _check_would_demand_a_token(from_phase, to_phase, tmp_path)

    assert told_to_sign == actually_demanded, (
        f"the hint and the gate disagree on {from_phase}->{to_phase}: "
        f"approval_required_for says {told_to_sign}, but the gate would "
        f"{'demand' if actually_demanded else 'not demand'} a token. "
        "The hint is the only guidance the lifecycle offers; when it disagrees with "
        "enforcement the operator signs for nothing (measured: 95 SMOKE->REFACTOR tokens)."
    )


def test_the_waived_edge_is_not_prescribed(tmp_path: Path) -> None:
    """The specific edge that produced the 95, named so a regression is legible."""
    assert not approval_required_for(_REPO_CONFIG, "SMOKE", "REFACTOR"), (
        "the hint still prescribes SMOKE->REFACTOR. SMOKE declares `autonomy: agent`, so "
        "_autonomy_waiver returns NOT_APPLICABLE and the token is never consulted. The "
        "config entry exists to run SmokeExecutionGateCheck, not to collect a signature."
    )


def test_the_gated_edge_is_still_prescribed(tmp_path: Path) -> None:
    """The fix must not silence the hint on the edge that IS owed (#1750's defect)."""
    assert approval_required_for(_REPO_CONFIG, "PLANNED", "RED"), (
        "the hint stopped prescribing PLANNED->RED, which the gate does enforce — "
        "this is #1750 in reverse: guidance that names no command for a gate that refuses."
    )
