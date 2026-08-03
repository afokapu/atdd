# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E071-UNIT-002-escape-phases-block-by-default
# Acceptance: acc:govern-lifecycle:E071-UNIT-002-escape-phases-block-by-default
# WMBT: wmbt:govern-lifecycle:E071
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E071-UNIT-002 — the escapes are a decision, and an unknown phase is fail-closed.

``phase_labels`` called BLOCKED and OBSOLETE ``out_of_scope`` with the note that
"no auto-close should target them anyway". That is a prediction, not a gate: the
enforcement simply did not name them, so an auto-close targeting one merged.

Both are now blocked, deliberately:

* **BLOCKED** — an escape entered by operator decision from any rung
  (``phase_machine.convention.yaml``). Its lifecycle is suspended *short of*
  REFACTOR, so a merge that closes it skips the same sign-off SMOKE does. It is
  the pre-SMOKE case wearing a different label.
* **OBSOLETE** — terminal (``transitions_to: []``), and retiring an issue is an
  operator transition. Letting a merge perform it would hand every author a
  one-label bypass of a rule whose disposition is ``strict``: relabel, merge,
  auto-close fires, lifecycle skipped.

The same reasoning settles a phase nobody has invented yet. Deriving the verdict
as the complement of the merge-eligible set means an unrecognised phase blocks
until someone widens that set on purpose — the list that had to be extended each
time a phase appeared was the bug, not the missing entry.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as mod


def _resolution(phase: str) -> dict:
    return {
        "pr_number": 4242,
        "issue_number": 4141,
        "phase_label": phase,
        "strategy": "api",
    }


@pytest.mark.parametrize("phase", ["BLOCKED", "OBSOLETE"])
def test_an_escape_phase_may_not_carry_a_live_auto_close(phase: str) -> None:
    violations = mod.evaluate_pr_merge_violations([_resolution(phase)])
    assert len(violations) == 1, (
        f"atdd:{phase} is an escape, not a merge-eligible phase: a merge that "
        "auto-closes from it retires the issue without the REFACTOR sign-off. "
        f"Got {violations!r}"
    )


def test_an_unrecognised_phase_blocks_rather_than_passes() -> None:
    """Fail-closed: a phase added to the machine later is blocked until admitted."""
    violations = mod.evaluate_pr_merge_violations([_resolution("VERIFIED")])
    assert len(violations) == 1, (
        "a phase outside the convention's merge-eligible set must block. Passing "
        "it would repeat this defect for the next phase the machine grows."
    )
