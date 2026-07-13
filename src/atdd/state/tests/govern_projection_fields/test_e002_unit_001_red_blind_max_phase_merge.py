# URN: test:govern-projection-fields:merge-projection-objects:E002-UNIT-001-red-blind-max-phase-merge
# Acceptance: acc:govern-projection-fields:E002-UNIT-001-red-blind-max-phase-merge
# WMBT: wmbt:govern-projection-fields:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: same-object phase divergence is NOT resolved by taking the further phase: with ours at RED carrying gate evidence and theirs at GREEN carrying none for the skipped PLANNED->RED gate, the driver emits no GREEN and no merged document, and signals a conflict naming the unevidenced gate Refs #1400.
"""Never blind max phase (E002-UNIT-001).

wagon: govern-projection-fields | feature: merge-projection-objects | phase: RED
WMBT: wmbt:govern-projection-fields:E002

"Take the further phase" is the reasonable-sounding rule that quietly destroys the lifecycle.
Here is the exact shape of it: A walks ``PLANNED -> RED`` honestly, with an operator token and
a failing test. B, on a stale branch, jumps straight to ``GREEN`` with nothing at all. Max
phase says GREEN, and the merge — which nobody reviews, because it is a *merge* — silently
promotes an unevidenced claim over an evidenced one and deletes the evidence of what happened.

So the driver checks the further phase against the evidence model, gate by gate, and refuses.
"""
from __future__ import annotations

from atdd.state import merge_driver
from atdd.state.ownership import RULE_MONOTONIC_GATED

from ._helpers import PLANNED_TO_RED, UID_X, document


def test_e002_unit_001_red_blind_max_phase_merge() -> None:
    """The further phase carries no evidence for the gate it skipped, so the merge conflicts."""
    base = document(phase="PLANNED")
    ours = document(phase="RED")            # walked the gate, with the evidence to show for it
    theirs = document(phase="GREEN")        # jumped it, with nothing

    result = merge_driver.merge_object(
        UID_X, base, ours, theirs,
        ours_evidence=PLANNED_TO_RED,
        theirs_evidence=(),                 # ...no evidence for PLANNED->RED, nor for RED->GREEN
    )

    # The driver does not silently emit GREEN.
    assert result.merged is None
    assert not result.ok
    assert result.exit_code == 1

    conflict = result.conflicts[0]
    assert conflict.field == "phase"
    assert conflict.rule == RULE_MONOTONIC_GATED
    # It says WHY: the further side skipped a gate it has no evidence for.
    assert "GREEN" in conflict.detail
    assert "no evidence" in conflict.detail
    assert "PLANNED->RED" in conflict.detail
    assert "never" in result.render() or "does not resolve" in conflict.detail

    # And the counterfactual that makes this a gate rather than a prohibition: the same
    # divergence, with theirs carrying evidence for every gate it passed through, merges.
    evidenced = merge_driver.merge_object(
        UID_X, base, ours, theirs,
        ours_evidence=PLANNED_TO_RED,
        theirs_evidence=(*PLANNED_TO_RED, "passing_test_evidence", "implementation_diff"),
    )
    assert evidenced.ok, evidenced.render()
    assert evidenced.merged["phase"] == "GREEN"
