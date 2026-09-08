# URN: component:atdd-plan-core:session-machine:plan_confirm_binds_issue:backend:domain
# Purpose: Enforce planner.plan.confirm-binds-an-issue (#1171) — atdd plan must not
#          lock (confirm) a decomposition that is not bound to an ATDD issue, so no
#          plan substrate is ever authored on an untracked branch. Upholds the
#          universal rule: every repo modification has an issue + branch + worktree.
"""planner.plan.confirm-binds-an-issue validator (#1171).

Behavioural gate: a fully-resolved session that is NOT bound to an issue must be
refused at confirm(). Pairs with the session-protocol convention-node of the same
rule_id and mirrors planner.plan.confirm-before-author.

Rule: planner.plan.confirm-binds-an-issue
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

_RULE = bind_rule("planner.plan.confirm-binds-an-issue")
_VALIDATOR_ID = "plan_confirm_binds_issue"
_LOC = "src/atdd/planner/commands/plan_session.py:PlanSession.confirm"


def _scan() -> List[Violation]:
    """A resolved-but-issue-less session must be refused at confirm()."""
    violations: List[Violation] = []
    session = PlanSession("confirm-binds-issue-probe", step=Step.RATIFY.value)
    # name must be verb-object (planner.wagon.name-is-verb-object, #1276); the
    # positive control below locks only if the kept name also passes that gate.
    session.add_unit(Unit(kind="wagon", ref="manage-probe", spec={"wagon": "manage-probe"}))
    session.units[0]["verdict"] = Verdict.KEEP.value
    assert session.issue_ref is None  # precondition: no local issue bound

    try:
        session.confirm()
        violations.append(Violation(
            rule_id=_RULE.rule_id, severity=_RULE.severity, location=_LOC,
            detail="confirm() locked a decomposition with no bound issue — the "
                   "confirm-binds-an-issue guard is missing or broken (plan substrate "
                   "could be authored on an untracked branch)",
        ))
    except SessionGateError:
        pass  # correct: refused until an issue is bound

    # positive control: once bound to a local issue (manifest slug), confirm proceeds
    session.issue_ref = "atdd-plan-binds-issue-at-confirm"
    try:
        session.confirm()
    except SessionGateError as exc:
        violations.append(Violation(
            rule_id=_RULE.rule_id, severity=_RULE.severity, location=_LOC,
            detail=f"confirm() refused a properly issue-bound session: {exc}",
        ))
    return violations


def test_confirm_binds_an_issue_is_enforced() -> None:
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan())
