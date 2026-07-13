# URN: test:govern-projection-fields:define-actor-ownership:D002-UNIT-001-not-implemented
# Acceptance: acc:govern-projection-fields:D002-UNIT-001-not-implemented
# WMBT: wmbt:govern-projection-fields:D002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: without owner_actor and last_lifecycle_actor on the projection object the single-owner body rule is not computable — neither the validator nor the merge driver can say who wrote either side — and the object carries both, so both can Refs #1400.
"""The single-owner rule needs an actor on the object to be computable (D002-UNIT-001).

wagon: govern-projection-fields | feature: define-actor-ownership | phase: RED
WMBT: wmbt:govern-projection-fields:D002

The policy says ``body`` conflicts *unless the single-owner rule proves safe*. That sentence
is unenforceable against an object that does not say who owns it: the validator cannot decide
whether the committing actor is the owner, and the merge driver, having refused the merge, can
only report that two anonymous strings differ.

So the rule's computability is a property of the **schema**: ``owner_actor`` says who owns the
body, and ``last_lifecycle_actor`` says who last moved the lifecycle — and the moment they are
absent, the report degrades to exactly the uselessness this acceptance exists to rule out.
"""
from __future__ import annotations

from atdd.state import merge_driver, ownership
from atdd.state.projection import FIELD_TYPES, REQUIRED_FIELDS

from ._helpers import UID_X, document, projection


def test_d002_unit_001_not_implemented() -> None:
    """Strip the actors and the rule is uncomputable; carry them and it is decidable."""
    policy = ownership.default_policy()

    # Without owner_actor, the driver cannot name the writer of either side — which is the
    # whole content of a conflict report on `body`.
    anonymous_ours = {"uid": UID_X, "phase": "PLANNED", "state": "ACTIVE", "body": "ours"}
    anonymous_theirs = {"uid": UID_X, "phase": "PLANNED", "state": "ACTIVE", "body": "theirs"}
    assert merge_driver.side_writer(anonymous_ours, "body", policy) == "<unknown>"
    assert merge_driver.side_writer(anonymous_theirs, "body", policy) == "<unknown>"

    # And the field-writer validator cannot accept or reject a body edit either: with no owner
    # on the object, there is nothing for the single-owner clause to compare the actor against.
    base = projection({"uid": UID_X, "phase": "PLANNED", "state": "ACTIVE", "body": "before"})
    head = projection(anonymous_ours)
    silent = ownership.check_diff(policy, base, head, actor="dev-b")
    assert silent.ok, "with no owner_actor the single-owner clause has nothing to say"

    # The schema carries both actors, which is what makes the rule computable at all — and
    # owner_actor is REQUIRED, so an object cannot be authored without one.
    assert "owner_actor" in FIELD_TYPES
    assert "last_lifecycle_actor" in FIELD_TYPES
    assert "owner_actor" in REQUIRED_FIELDS

    # With them, the same body edit by a second writer is decidable — and decided.
    owned_head = projection(document(body="ours", owner_actor="dev-a"))
    owned_base = projection(document(body="before", owner_actor="dev-a"))
    judged = ownership.check_diff(policy, owned_base, owned_head, actor="dev-b")
    assert not judged.ok
    assert judged.violations[0].path == "body"
    assert "dev-a" in judged.violations[0].detail
