# URN: test:reconcile-local-store:guard-dirty-store:C002-UNIT-003-blast-radius-refuses-and-the-override-is-not-a-bypass
# Acceptance: acc:reconcile-local-store:C002-UNIT-003-blast-radius-refuses-and-the-override-is-not-a-bypass
# WMBT: wmbt:reconcile-local-store:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: guard_deletions refuses a deletion set over the proportional or the absolute blast radius, allows a routine one under the safe floor, and treats allow_deletions as an assertion of the expected count that must match exactly rather than as a force flag. Refs #1580.
"""The blast radius, and why its override cannot be a bypass (C002-UNIT-003).

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C002

Absence stops meaning deletion in C002-UNIT-004, which removes the *specific* path that caused
the incident. This guard exists because that is not the same as removing the *class*: any future
path that computes a deletion set — a mass tombstone, an over-eager compaction, a merge that
resolves badly, a control root resolved to the wrong project — arrives at the same raw ``DELETE``
loop. So the count itself is guarded, wherever it came from.

Three rules, in the order they are judged:

- **A routine retirement is not a mass deletion.** At or below :data:`SAFE_DELETIONS`, nothing
  is refused whatever the proportion. Retiring 2 objects from a store of 6 is 33% of it and is
  also a Tuesday, and a guard that refuses Tuesdays is one operators learn to route around.
- **Proportion catches the small store.** Above that floor, more than
  :data:`MAX_DELETION_FRACTION` of the work_items is refused. Half of a 20-object store is not
  a large number and is still a catastrophe.
- **Absolute count catches the large one.** More than :data:`MAX_ABSOLUTE_DELETIONS` is refused
  however small the proportion. 60 objects out of 5000 is a rounding error proportionally, and
  is still 60 things somebody has to get back.

``allow_deletions`` is the operator's way through, and it is deliberately **not** a force flag.
It asserts *how many* deletions they expect; a value that does not match reality is refused just
as loudly as no value at all. That distinction is the whole point — ``--force`` answers "do it
anyway", which is the question that was never asked during the incident. This asks "how many?",
and a wrong answer means the operator does not know what they are about to do.

Refs #1580.
"""
from __future__ import annotations

import pytest

from atdd.state.reconcile import (
    MAX_ABSOLUTE_DELETIONS,
    MAX_DELETION_FRACTION,
    SAFE_DELETIONS,
    MassDeletionRefused,
    guard_deletions,
)


def _uids(count: int) -> list:
    return [f"wi_01HF7YAT00M78607F{index:09d}" for index in range(count)]


def test_c002_unit_003_a_routine_retirement_is_not_refused() -> None:
    """At or below the safe floor nothing is refused, however small the store."""
    # 5 of 6 is 83% — far past the proportional rule — but it is under the floor, and the
    # floor is deliberately judged first. Tiny stores are otherwise unusable.
    guard_deletions(_uids(SAFE_DELETIONS), existing=SAFE_DELETIONS + 1)
    guard_deletions([], existing=0)  # nothing to delete: never a refusal


def test_c002_unit_003_proportion_refuses_a_small_store_mass_deletion() -> None:
    """Above the floor, more than the permitted fraction of the store is refused."""
    existing = 20
    doomed = _uids(8)  # 40% — over the fraction, under the absolute cap, over the floor
    assert len(doomed) > SAFE_DELETIONS
    assert len(doomed) <= MAX_ABSOLUTE_DELETIONS
    assert len(doomed) / existing > MAX_DELETION_FRACTION

    with pytest.raises(MassDeletionRefused) as refused:
        guard_deletions(doomed, existing=existing)

    message = str(refused.value)
    assert "8" in message and "20" in message, f"the refusal must show its arithmetic: {message}"
    assert refused.value.existing == existing
    assert len(refused.value.doomed) == 8

    # A deletion set under the fraction passes at the same store size.
    guard_deletions(_uids(4), existing=existing)


def test_c002_unit_003_absolute_cap_refuses_a_large_store_mass_deletion() -> None:
    """Past the absolute cap it is refused however small the proportion."""
    doomed = _uids(MAX_ABSOLUTE_DELETIONS + 1)
    existing = (MAX_ABSOLUTE_DELETIONS + 1) * 100  # 1% — comfortably under the fraction
    assert len(doomed) / existing < MAX_DELETION_FRACTION

    with pytest.raises(MassDeletionRefused) as refused:
        guard_deletions(doomed, existing=existing)
    assert str(MAX_ABSOLUTE_DELETIONS) in str(refused.value)


def test_c002_unit_003_the_override_is_an_assertion_not_a_bypass() -> None:
    """``allow_deletions`` must state the true count; a wrong number is still refused."""
    doomed = _uids(25)
    existing = 30

    # Refused with no assertion at all.
    with pytest.raises(MassDeletionRefused):
        guard_deletions(doomed, existing=existing)

    # Refused with the WRONG assertion — this is the case that separates an assertion from a
    # force flag. An operator who believes they are deleting 5 things must not delete 25.
    with pytest.raises(MassDeletionRefused) as mismatched:
        guard_deletions(doomed, existing=existing, allow_deletions=5)
    message = str(mismatched.value)
    assert "5" in message and "25" in message, (
        f"a mismatched assertion must quote both numbers back: {message}"
    )
    assert mismatched.value.allowed == 5

    # Allowed only when the operator's number matches what is actually about to happen.
    guard_deletions(doomed, existing=existing, allow_deletions=25)


def test_c002_unit_003_the_thresholds_are_ordered_so_the_guard_can_fire() -> None:
    """The constants must leave every rule reachable — a guard that cannot fire is a stub."""
    assert 0 < SAFE_DELETIONS < MAX_ABSOLUTE_DELETIONS, (
        "the floor must sit below the cap, or one of the two rules is dead code"
    )
    assert 0 < MAX_DELETION_FRACTION < 1, (
        "a fraction of 0 refuses everything and a fraction of 1 refuses nothing"
    )
