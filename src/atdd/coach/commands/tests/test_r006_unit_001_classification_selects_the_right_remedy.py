# URN: test:govern-lifecycle:R006-UNIT-001-classification-selects-the-right-remedy
# Acceptance: acc:govern-lifecycle:R006-UNIT-001-classification-selects-the-right-remedy
# WMBT: wmbt:govern-lifecycle:R006
# Phase: RED
# Layer: backend.domain
# Assertion: behavioral
"""R006-UNIT-001 — each divergence lands in the repair class whose remedy is
correct for the evidence available, and a repaired record re-classifies as a
no-op.

``classify`` is pure on purpose. The whole verb turns on picking the right
remedy from two facts — the store floor and whether a merged PR closed the issue
— and a classifier reachable only through ``gh`` could never be exercised across
its whole matrix. Everything below drives it directly.

The direction of truth is the thing under test. The store is honest and stale;
the label is the unearned artifact. So no class may ever set the store from the
label, and only the one class with proof that the work landed is allowed to
advance the store at all.

Issue #1338.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.issue_reconcile_state import (
    CLASS_IN_SYNC,
    CLASS_LEGACY_UNDRIVEN,
    CLASS_PROJECTION_LAG,
    CLASS_UNEARNED_NO_EVIDENCE,
    CLASS_UNEARNED_WORK_LANDED,
    CLASS_UNKNOWN_TO_STORE,
    classify,
    missing_steps,
)

pytestmark = [pytest.mark.coach]


def test_agreeing_label_and_store_is_a_noop():
    """Class 0: nothing to repair, and nothing is attempted."""
    repair = classify(1, "REFACTOR", "REFACTOR", merged=True)
    assert repair.repair_class == CLASS_IN_SYNC
    assert repair.is_noop, (
        "An in-sync record must plan no action at all; planning a redundant "
        "write is how a repair verb becomes a source of drift."
    )


def test_label_behind_store_is_projection_lag_and_re_projects():
    """Class 1: the store already holds the truth — re-derive the label from it."""
    repair = classify(2, "INIT", "GREEN", merged=False)
    assert repair.repair_class == CLASS_PROJECTION_LAG
    assert repair.reproject_to == "GREEN"
    assert repair.transitions == (), (
        "Projection lag is a rendering problem, not a lifecycle one. Advancing "
        "the store here would invent transitions to fix a stale label."
    )


def test_unearned_complete_with_a_merged_pr_replays_the_missing_steps():
    """Class 2: the work landed, so the store earns the phases it is missing.

    This is the #1434 signature — the smoking-gun record whose own store sat at
    SMOKE while its label claimed COMPLETE.
    """
    repair = classify(1434, "COMPLETE", "SMOKE", merged=True)
    assert repair.repair_class == CLASS_UNEARNED_WORK_LANDED
    assert repair.transitions == ("REFACTOR", "COMPLETE"), (
        "The replay must walk the phase machine one legal single step at a "
        f"time; got {repair.transitions}."
    )
    assert repair.reproject_to is None, (
        "A replay and a re-projection are mutually exclusive remedies."
    )


def test_unearned_complete_without_merge_evidence_does_not_advance_the_store():
    """Class 3: no proof the work landed, so the label is simply false."""
    repair = classify(3, "COMPLETE", "GREEN", merged=False)
    assert repair.repair_class == CLASS_UNEARNED_NO_EVIDENCE
    assert repair.reproject_to == "GREEN"
    assert repair.transitions == (), (
        "Without a merged PR there is no evidence the work landed. Advancing "
        "the store on the label's say-so would launder the corruption into the "
        "source of truth — the one thing the repair must never do."
    )


def test_a_record_the_store_does_not_know_is_not_guessed_at():
    """Class 5: absence is not drift, and the suspect label is not a fallback."""
    repair = classify(11, "COMPLETE", None, merged=True)
    assert repair.repair_class == CLASS_UNKNOWN_TO_STORE
    assert repair.is_noop, (
        "With no store floor there is nothing to reason from. Seeding the store "
        "from the label would take the corrupted artifact as truth."
    )
    assert "reconcile" in repair.reason, (
        "The refusal must name `atdd coach reconcile` — the verb that backfills "
        "existence — so the operator is not left guessing."
    )


def test_replaying_a_repaired_record_is_a_noop():
    """Idempotence: class 2 lands at COMPLETE, and re-running finds class 0."""
    before = classify(1434, "COMPLETE", "SMOKE", merged=True)
    landed_at = before.transitions[-1]
    after = classify(1434, "COMPLETE", landed_at, merged=True)
    assert after.repair_class == CLASS_IN_SYNC
    assert after.is_noop, (
        "Re-running the verb on a record it already repaired must be a no-op; "
        "a repair that is not idempotent cannot be run safely twice."
    )


@pytest.mark.parametrize(
    "store, target, expected",
    [
        ("SMOKE", "COMPLETE", ("REFACTOR", "COMPLETE")),
        ("PLANNED", "COMPLETE", ("RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE")),
        ("COMPLETE", "COMPLETE", ()),
        ("REFACTOR", "GREEN", ()),
        ("BLOCKED", "COMPLETE", ()),
    ],
)
def test_missing_steps_walks_only_forward_single_steps_on_the_spine(store, target, expected):
    """The replay path is the phase machine's forward spine and nothing else.

    A backwards or off-spine "step" is not a transition the machine has an edge
    for, so synthesising one would be exactly the fabrication class 4 exists to
    prevent — just wearing a different label.
    """
    assert missing_steps(store, target) == expected


def test_class_4_is_decided_before_class_2():
    """Ordering is load-bearing, not incidental.

    ``store=INIT`` + ``label=COMPLETE`` + a merged PR satisfies class 2's
    conditions on its face. If class 2 were tested first, these 82 records would
    each be handed a six-step replay — the fabrication. The refusal must win.
    """
    repair = classify(4, "COMPLETE", "INIT", merged=True)
    assert repair.repair_class == CLASS_LEGACY_UNDRIVEN, (
        "A merged INIT-floored record was classified as a replay candidate. "
        "Class 4 must be decided before class 2."
    )
    assert repair.transitions == ()
