# URN: test:govern-lifecycle:R006-UNIT-002-class-4-refuses-to-fabricate-history
# Acceptance: acc:govern-lifecycle:R006-UNIT-002-class-4-refuses-to-fabricate-history
# WMBT: wmbt:govern-lifecycle:R006
# Phase: RED
# Layer: application
# Assertion: behavioral
"""R006-UNIT-002 — the legacy-undriven refusal fires, writes nothing, and cannot
be flagged into fabricating a history.

**A guard that is only ever run against records it lets through has never been
shown to fail.** So this file does not merely assert "class 4 refuses". It plants
the class-4 signature into the apply path with both writers instrumented, watches
the refusal fire, and proves the writers were never reached — then plants the
*neighbouring* signature (same shape, non-INIT floor) and watches the same code
path repair it. A refusal that fired for everything would be indistinguishable
from a broken verb.

WHY THIS REFUSAL EXISTS
    82 records carry ``store=INIT`` with ``label=COMPLETE``. Their floor is INIT
    not because the bug caught them at INIT but because the store was never
    driven for them at all. Replaying INIT -> PLANNED -> RED -> GREEN -> SMOKE ->
    REFACTOR -> COMPLETE would fabricate an audit trail that never happened —
    trading a *wrong* record for a *fraudulent* one. A wrong label is
    recoverable; an invented history every downstream reader now trusts is not.

    Operator-confirmed: "Class 4 refusal confirmed."

Issue #1338.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.issue_reconcile_state import (
    CLASS_LEGACY_UNDRIVEN,
    CLASS_UNEARNED_WORK_LANDED,
    apply_repair,
    classify,
)

pytestmark = [pytest.mark.coach]

# The planted fault: the exact live signature of the 82 legacy-undriven records.
LEGACY_UNDRIVEN = dict(label_phase="COMPLETE", store_phase="INIT", merged=True)

# Its neighbour — identical in every respect except a floor the store actually
# earned. This one MUST be repaired, or the refusal above proves nothing.
DRIVEN = dict(label_phase="COMPLETE", store_phase="SMOKE", merged=True)


class _Writers:
    """Records every authoritative write the apply path attempts."""

    def __init__(self):
        self.transitions: list = []
        self.reprojections: list = []

    def transition(self, issue_number, phase, *, target_dir=None):
        self.transitions.append((issue_number, phase))
        return 0

    def reproject(self, issue_number):
        self.reprojections.append(issue_number)
        return "INIT"


def _apply(signature, *, allow_legacy_undriven=False):
    writers = _Writers()
    repair = classify(9001, **signature)
    rc = apply_repair(
        repair,
        allow_legacy_undriven=allow_legacy_undriven,
        transition=writers.transition,
        reproject=writers.reproject,
    )
    return repair, rc, writers


def test_the_planted_fault_really_is_a_class_4_record():
    """Assert the fault LANDED before asserting anything about the response.

    If the planted signature silently stopped classifying as class 4, every
    assertion below would pass against a record that was never the fault at all
    — the guard would be green because it was never asked the question.
    """
    repair, _, _ = _apply(LEGACY_UNDRIVEN)
    assert repair.repair_class == CLASS_LEGACY_UNDRIVEN, (
        f"The planted legacy-undriven signature classified as "
        f"{repair.class_name!r}, so this file is not exercising the refusal."
    )
    assert repair.refused is True


def test_the_refusal_fires_and_is_non_zero():
    """The verb must fail loudly, not skip quietly."""
    _, rc, _ = _apply(LEGACY_UNDRIVEN)
    assert rc != 0, (
        "A class-4 record exited 0. A refusal that reports success is a refusal "
        "no operator will ever notice."
    )


def test_the_refusal_writes_absolutely_nothing():
    """Default action for class 4 is none — not 'a smaller repair'."""
    _, _, writers = _apply(LEGACY_UNDRIVEN)
    assert writers.transitions == [], (
        f"A class-4 record drove {writers.transitions} through the phase "
        "machine. That is the fabricated audit trail this refusal exists to "
        "prevent."
    )
    assert writers.reprojections == [], (
        "A class-4 record was silently re-projected. Class 4 is never repaired "
        "implicitly — it requires an explicit operator decision."
    )


def test_the_refusal_explains_itself():
    """An unexplained refusal gets bypassed; a reasoned one gets respected."""
    repair, _, _ = _apply(LEGACY_UNDRIVEN)
    reason = repair.reason.lower()
    assert "fabricate" in reason or "invent" in reason, (
        f"The refusal must name what it is refusing to do; got: {repair.reason}"
    )
    assert "--allow-legacy-undriven" in repair.reason, (
        "The refusal must name the operator flag, or the operator has no path "
        "forward except to work around the verb."
    )


def test_the_operator_flag_re_projects_down_and_still_never_replays():
    """The escape hatch corrects the label; it does not buy a history.

    This is the load-bearing half. An operator-overridable refusal that unlocks
    a replay would only *delay* the fabrication. The flag authorises re-deriving
    the label DOWN to the honest floor and nothing else, so a fabricated history
    is unreachable by construction rather than merely discouraged.
    """
    _, rc, writers = _apply(LEGACY_UNDRIVEN, allow_legacy_undriven=True)
    assert rc == 0, "The operator-authorised path must succeed."
    assert writers.reprojections == [9001], (
        "The authorised path must re-project the label from the store."
    )
    assert writers.transitions == [], (
        f"--allow-legacy-undriven unlocked a replay ({writers.transitions}). No "
        "flag may authorise synthesising a phase history."
    )


def test_the_guard_is_capable_of_letting_a_real_repair_through():
    """The second, orthogonal assertion: the refusal discriminates.

    Same label, same merge evidence, same code path — only the store floor
    differs. If this record were refused too, the 'refusal' would just be the
    verb not working.
    """
    repair, rc, writers = _apply(DRIVEN)
    assert repair.repair_class == CLASS_UNEARNED_WORK_LANDED
    assert rc == 0
    assert writers.transitions == [(9001, "REFACTOR"), (9001, "COMPLETE")], (
        f"A legitimately-driven record was not repaired; got "
        f"{writers.transitions}. The refusal must key on the INIT floor, not "
        "fire blanket across the COMPLETE signature."
    )


def test_a_refused_replay_step_stops_the_walk_rather_than_forcing_it():
    """If the phase machine refuses mid-replay, the verb stops there.

    The store keeps whatever it legally earned and nothing is forced past a
    gate — the replay is a sequence of real transitions, not a backdoor around
    them.
    """
    attempted: list = []

    def refusing_transition(issue_number, phase, *, target_dir=None):
        attempted.append(phase)
        return 1 if phase == "REFACTOR" else 0

    rc = apply_repair(
        classify(9002, **DRIVEN),
        transition=refusing_transition,
        reproject=lambda n: "SMOKE",
    )
    assert rc != 0, "A refused replay step must surface as a non-zero exit."
    assert attempted == ["REFACTOR"], (
        f"The walk continued past a refused gate (attempted {attempted}). Each "
        "step must be earned; a replay that skips a refusal is the raw label "
        "write wearing a new name."
    )
