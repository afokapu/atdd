# URN: component:atdd-plan-core:session-machine:plan_confirm_before_author:backend:domain
# Purpose: Enforce planner.plan.confirm-before-author (#1139) — the atdd plan
#          session must refuse to author any substrate before the operator's
#          Confirm lock. Strict disposition: the conversational->deterministic
#          boundary must hold in code, not just by convention.
"""planner.plan.confirm-before-author validator (#1139).

Behavioural gate: exercises the real PlanSession author pass and refuses if it
would invoke an atdd-author writer before the session is locked. Pairs with the
session-protocol convention-node of the same rule_id.

Rule: planner.plan.confirm-before-author
Run:  atdd validate planner
"""
from __future__ import annotations

from typing import List

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.planner.commands.plan_session import (
    PlanSession, SessionGateError, Step, Unit, Verdict,
)

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.plan.confirm-before-author")
_VALIDATOR_ID = "plan_confirm_before_author"
_LOC = "src/atdd/planner/commands/plan_session.py:PlanSession.author"


def _scan() -> List[Violation]:
    """A kept unit in an UNLOCKED session must never reach an author writer."""
    violations: List[Violation] = []
    session = PlanSession("confirm-before-author-probe", step=Step.RATIFY.value)
    session.add_unit(Unit(kind="wagon", ref="probe", spec={"wagon": "probe"}))
    session.units[0]["verdict"] = Verdict.KEEP.value
    assert session.locked is False  # precondition: not yet confirmed

    wrote: list = []
    try:
        session.author(lambda kind, spec: wrote.append((kind, spec)))
        violations.append(Violation(
            rule_id=_RULE.rule_id, severity=_RULE.severity, location=_LOC,
            detail="author() did not refuse before the Ratify lock — the "
                   "confirm-before-author boundary is missing or broken",
        ))
    except SessionGateError:
        pass  # correct: refused before lock

    if wrote:
        violations.append(Violation(
            rule_id=_RULE.rule_id, severity=_RULE.severity, location=_LOC,
            detail=f"an atdd author writer was invoked before confirm: {wrote!r}",
        ))
    return violations


def test_confirm_before_author_is_enforced() -> None:
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan())
