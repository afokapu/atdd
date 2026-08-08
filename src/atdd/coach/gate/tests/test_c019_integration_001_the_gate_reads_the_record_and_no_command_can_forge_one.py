# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C019-INTEGRATION-001-the-gate-reads-the-record-and-no-command-can-forge-one
# Acceptance: acc:govern-lifecycle:C019-INTEGRATION-001-the-gate-reads-the-record-and-no-command-can-forge-one
# WMBT: wmbt:govern-lifecycle:C019
# Phase: RED
# Layer: integration
# Assertion: behavioral
# Purpose: the attestation is worth exactly as much as its unforgeability — if any CLI verb can write one, the gate is reading a claim again with extra steps
"""C019-INTEGRATION-001 — the dispatch writes it, and nothing else can.

This is #1602's thesis applied to dispatch. That issue found that everything the
repo called smoke evidence was producible without running a test: the #1151
self-skip validator is a static source scan that proves a test CANNOT SKIP but
never that it RAN, and ``.atdd/smoke-evidence/<N>.yaml`` is written by ``atdd
validate coder --smoke-required``, a command that runs no test. Its conclusion,
stated in ``smoke_attestation``'s module docstring: **if you can type it, it is
not an attestation.**

The same trap is open here in a worse form. A journey-map REGISTRATION is a
declaration — the consumer saying "these actions route to these trains". Reading
the registration and reporting "instantiated" would be precisely the
descriptive-not-systemic failure #1618 refused, one layer up: a dead route table
satisfying the letter of the check. So the gate reads the RECORD of a dispatch
that happened, and this file holds the line that no command can manufacture one.

FAILURE POSTURE, AND WHY SWALLOWING IS SAFE HERE. The dispatch must never break
on a failed write — same reasoning as the pytest hook, which "must not break the
run it is observing". That is safe ONLY because the consumer fails closed: a
swallowed write means no attestation, and no attestation reads as "no dispatch
happened". The two halves conspire so any failure to record reads as stricter,
never laxer. Both halves are asserted below; either alone is a bug.

RED state: ``atdd.state.journey_evidence`` does not exist and
``InterlockingRunner.execute`` records nothing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_TRAIN = "0007-enforce-extension-conventions"


def test_a_real_dispatch_writes_its_own_attestation(tmp_path: Path):
    """C019-INTEGRATION-001: the fact is captured where it exists."""
    from atdd.state.journey_evidence import journey_dispatches, open_state_store
    from atdd.coach.gate.tests._c019_support import dispatch_through_runner, seeded_repo

    worktree, uid = seeded_repo(tmp_path)
    dispatch_through_runner(worktree, action="collaborate")

    with open_state_store(control_root=worktree) as store:
        records = journey_dispatches(store, uid)

    assert len(records) == 1
    run = records[0]
    assert run.action == "collaborate"
    assert run.train_id, "the resolved train id is what makes the record traceable"
    assert run.commit_sha, "so an attestation from three commits ago cannot satisfy today"
    assert run.duration_s > 0.0, (
        "a zero duration means nothing executed — the #1192 shape, where a 'live "
        "end-to-end' smoke returned in 0.12s with no worker running"
    )
    assert run.dirty in (True, False), (
        "recorded, never gated on: a dirty tree is the normal state while working, "
        "but an attestation implying the committed tree ran would be the same lie"
    )


def test_no_cli_verb_in_the_package_can_write_a_dispatch_attestation():
    """C019-INTEGRATION-001: if you can type it, it is not an attestation.

    Asserted over the command surface, the way #1602 holds this line with
    ``test_operator_typed_stamp_is_not_accepted_as_execution_evidence``. A verb
    that writes one turns the record back into a stamp, and the gate back into a
    reader of claims — silently, and with every test above still green.
    """
    from atdd.coach.gate.tests._c019_support import cli_writers_of_journey_attestations

    writers = cli_writers_of_journey_attestations()
    assert writers == [], (
        f"these CLI paths can write a dispatch attestation: {writers}. There must "
        f"be no such verb — the pytest-hook precedent (#1602) keeps the producer "
        f"inside the thing being observed, never on the command surface"
    )


def test_an_attestation_against_an_unknown_work_item_raises(tmp_path: Path):
    """C019-INTEGRATION-001: loud beats evidence no gate can ever find.

    Same choice ``record_smoke_execution`` makes on the ``events.object_uid``
    foreign key: recording against a uid nothing owns produces an orphan record
    that no reader will ever locate, which is worse than failing loudly.
    """
    from atdd.state.journey_evidence import (
        JourneyDispatch,
        JourneyAttestationError,
        open_state_store,
        record_journey_dispatch,
    )
    from atdd.coach.gate.tests._c019_support import seeded_repo

    worktree, _ = seeded_repo(tmp_path)
    with open_state_store(control_root=worktree) as store:
        with pytest.raises(JourneyAttestationError):
            record_journey_dispatch(
                store,
                "no-such-work-item",
                JourneyDispatch(action="collaborate", train_id=_TRAIN, duration_s=0.5),
            )


def test_a_failed_write_is_swallowed_by_dispatch_and_reads_as_no_dispatch(tmp_path: Path):
    """C019-INTEGRATION-001: both halves of the fail-closed conspiracy."""
    from atdd.coach.gate.decision import GateContext, GateVerdict
    from atdd.coach.gate.train_instantiation_check import TrainInstantiationGateCheck
    from atdd.coach.gate.tests._c019_support import (
        dispatch_through_runner,
        seeded_repo,
        unwritable_store,
    )

    worktree, _ = seeded_repo(tmp_path)

    with unwritable_store(worktree):
        # Half one: the dispatch completes. An observer must not break the thing
        # it observes, so the write failure is logged and swallowed.
        dispatch_through_runner(worktree, action="collaborate")

    # Half two: with nothing recorded, the gate refuses. Silence is stricter.
    result = TrainInstantiationGateCheck().run(
        GateContext(999019, "SMOKE", "REFACTOR", worktree)
    )
    assert result.verdict is not GateVerdict.PASS
    assert result.passed is False


def test_an_attestation_from_another_commit_does_not_satisfy_head(tmp_path: Path):
    """C019-INTEGRATION-001: the route dispatched must be the route advanced."""
    from atdd.coach.gate.decision import GateContext, GateVerdict
    from atdd.coach.gate.train_instantiation_check import TrainInstantiationGateCheck
    from atdd.coach.gate.tests._c019_support import (
        commit_something,
        dispatch_through_runner,
        seeded_repo,
    )

    worktree, _ = seeded_repo(tmp_path)
    dispatch_through_runner(worktree, action="collaborate")
    commit_something(worktree)  # HEAD moves; the attestation stays where it was

    result = TrainInstantiationGateCheck().run(
        GateContext(999019, "SMOKE", "REFACTOR", worktree)
    )
    assert result.verdict is not GateVerdict.PASS
    assert "HEAD" in result.message or "stale" in result.message.lower()
