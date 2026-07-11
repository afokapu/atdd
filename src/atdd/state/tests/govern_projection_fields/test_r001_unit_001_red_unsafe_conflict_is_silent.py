# URN: test:govern-projection-fields:merge-projection-objects:R001-UNIT-001-red-unsafe-conflict-is-silent
# Acceptance: acc:govern-projection-fields:R001-UNIT-001-red-unsafe-conflict-is-silent
# WMBT: wmbt:govern-projection-fields:R001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: an unsafe same-object divergence is not merely refused: the conflict report names the field body, the writer on each side, and the conflict-unless-single-owner rule that rejected it Refs #1400.
"""A conflict that names nothing is a conflict nobody can resolve (R001-UNIT-001).

wagon: govern-projection-fields | feature: merge-projection-objects | phase: RED
WMBT: wmbt:govern-projection-fields:R001

Refusing the merge is the easy half. The half that decides whether the model is usable is what
the operator is told: "CONFLICT (content): merge conflict in wi_01HF7YAT….yaml" is a filename
and an apology. What they need is the three things that let them go and fix it — *which field*
diverged, *who wrote each side*, and *which rule* refused to choose between them.

The writers come off the object itself (``owner_actor``), which is why D002 puts them there.
"""
from __future__ import annotations

from atdd.state import merge_driver, ownership
from atdd.state.ownership import RULE_SINGLE_OWNER

from ._helpers import UID_X, document


def test_r001_unit_001_red_unsafe_conflict_is_silent() -> None:
    """The report names the field, both sides' writers, and the failing ownership rule."""
    policy = ownership.default_policy()
    base = document(body="the original body", owner_actor="dev-a")
    ours = document(body="A's rewrite", owner_actor="dev-a")
    theirs = document(body="B's rewrite", owner_actor="dev-b")

    result = merge_driver.merge_object(UID_X, base, ours, theirs, policy=policy)

    assert not result.ok
    assert result.merged is None

    conflict = result.conflicts[0]
    # 1. The field.
    assert conflict.field == "body"
    # 2. Both sides' writers.
    assert conflict.ours_writer == "dev-a"
    assert conflict.theirs_writer == "dev-b"
    # 3. The rule that rejected the merge — the one declared in the policy, by its name.
    assert conflict.rule == RULE_SINGLE_OWNER
    assert policy.rule_of("body") == RULE_SINGLE_OWNER

    rendered = conflict.render()
    for fragment in ("body", "dev-a", "dev-b", RULE_SINGLE_OWNER):
        assert fragment in rendered, fragment

    # The values are carried too, so a review tool can show them without re-reading the tree.
    assert conflict.ours_value == "A's rewrite"
    assert conflict.theirs_value == "B's rewrite"
