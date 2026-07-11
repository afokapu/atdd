# URN: test:govern-projection-fields:define-actor-ownership:D002-UNIT-002-holds
# Acceptance: acc:govern-projection-fields:D002-UNIT-002-holds
# WMBT: wmbt:govern-projection-fields:D002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: owner_actor and last_lifecycle_actor on the projection object make the single-owner body rule computable in both consumers: the field-writer validator accepts the owner's body edit and rejects a second writer's, and the merge driver's conflict report names the writer on each side Refs #1400.
"""The actors on the object make the rule decidable, for both readers (D002-UNIT-002).

wagon: govern-projection-fields | feature: define-actor-ownership | phase: RED
WMBT: wmbt:govern-projection-fields:D002

Two consumers, one pair of fields:

- the **field-writer validator** asks "is the actor who committed this body edit the object's
  owner?" — and answers it from ``owner_actor``;
- the **merge driver**, having refused a divergent body, answers "who wrote each side?" — from
  ``owner_actor`` for authoring-owned fields, and from ``last_lifecycle_actor`` for
  lifecycle-owned ones, because the person who last moved the phase is not necessarily the
  person who owns the body.

Both answers are what turns "conflict" into something an operator can act on.
"""
from __future__ import annotations

from atdd.state import merge_driver, ownership
from atdd.state.ownership import RULE_SINGLE_OWNER

from ._helpers import UID_X, document, projection


def test_d002_unit_002_holds() -> None:
    """The validator decides a body edit, and the driver names both writers on a conflict."""
    policy = ownership.default_policy()
    base = projection(document(body="the original", owner_actor="dev-a"))

    # 1. The validator ACCEPTS the owner's own body edit...
    owner_edit = projection(document(body="the owner's rewrite", owner_actor="dev-a"))
    assert ownership.check_diff(policy, base, owner_edit, actor="dev-a").ok

    # ...and REJECTS a second writer's, naming the owner and the rule that refused it.
    intruder = ownership.check_diff(policy, base, owner_edit, actor="dev-b")
    assert not intruder.ok
    violation = intruder.violations[0]
    assert violation.path == "body"
    assert violation.rule == RULE_SINGLE_OWNER
    assert "dev-a" in violation.detail
    assert violation.actor == "dev-b"

    # 2. The driver EXPLAINS a divergent body: both sides' writers, by name.
    ours = document(body="ours", owner_actor="dev-a")
    theirs = document(body="theirs", owner_actor="dev-b")
    result = merge_driver.merge_object(UID_X, base[UID_X], ours, theirs, policy=policy)

    assert not result.ok
    conflict = result.conflicts[0]
    assert conflict.field == "body"
    assert conflict.rule == RULE_SINGLE_OWNER
    assert conflict.ours_writer == "dev-a"
    assert conflict.theirs_writer == "dev-b"
    assert "dev-a" in conflict.render() and "dev-b" in conflict.render()

    # 3. A lifecycle-owned field is attributed to the LIFECYCLE actor, not to the body's owner:
    #    the two are different people and the report must not confuse them.
    ours_phase = document(phase="RED", owner_actor="dev-a", last_lifecycle_actor="coach-bot-less")
    assert merge_driver.side_writer(ours_phase, "phase", policy) == "coach-bot-less"
    assert merge_driver.side_writer(ours_phase, "body", policy) == "dev-a"
