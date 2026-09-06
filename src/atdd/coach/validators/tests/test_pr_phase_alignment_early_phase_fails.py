# URN: test:author-atdd-substrate:pr-phase-alignment:PRGATE-UNIT-001-early-phase-emits-violation
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""PRGATE-UNIT-001 — merging code while the issue never left INIT must FAIL.

    Code files in a PR whose linked issue is at INIT or PLANNED emit a
    structured `Violation`, not an opaque warning string.

`evaluate_phase_violations` already detects this exactly — it classifies
`src/**` as code (#1632/C014) and matches INIT/PLANNED — but emits a bare `str`
under "legacy warn semantics". Only GREEN produces a `Violation`. A warning
string is ratcheted opaquely and fails nothing, so a PR that skipped the entire
lifecycle merges green.

Observed: #1488 (PR #1784) and #1787 (PR #1788) both merged with their issues
still at `atdd:INIT`. `validate-coach` passed on both, and CI's own
`test_evaluate_phase_violations_returns_warning_string_for_init_with_code`
records the warn-only behaviour as intended.

GREEN-without-SMOKE is severity 4 (COACH-PRGATE-0003). Skipping INIT → SMOKE
entirely is a superset of that omission and cannot be the weaker signal.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators._violation import Violation
from atdd.coach.validators.test_pr_phase_alignment import (
    RULE_ID_PRGATE_EARLY,
    evaluate_phase_violations,
)

_CODE = {"code": ["src/atdd/substrate/coherence.py"], "test": [], "plan": [], "other": []}


@pytest.mark.parametrize("phase", ["INIT", "PLANNED"])
def test_early_phase_with_code_emits_structured_violation(phase: str) -> None:
    items = evaluate_phase_violations(1788, 1787, phase, _CODE)
    assert items, f"{phase} with code must not be silent"
    assert all(isinstance(i, Violation) for i in items), (
        f"{phase} with code must emit a structured Violation, not an opaque "
        f"warning string; got {[type(i).__name__ for i in items]}"
    )
    assert items[0].rule_id == RULE_ID_PRGATE_EARLY
    assert phase in items[0].detail


@pytest.mark.parametrize("phase", ["INIT", "PLANNED"])
def test_early_phase_without_code_stays_quiet(phase: str) -> None:
    """Plan-only PRs at INIT are exactly what INIT is for."""
    plan_only = {"code": [], "test": [], "plan": ["plan/x.yaml"], "other": []}
    assert evaluate_phase_violations(1, 2, phase, plan_only) == []
