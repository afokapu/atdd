# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C019-UNIT-002-the-gate-answers-in-four-states-and-never-silently-passes
# Acceptance: acc:govern-lifecycle:C019-UNIT-002-the-gate-answers-in-four-states-and-never-silently-passes
# WMBT: wmbt:govern-lifecycle:C019
# Phase: RED
# Layer: unit
# Assertion: behavioral
# Purpose: the gate's whole value is distinguishing "I confirmed it runs" from "it is merely declared" from "I could not tell" — collapsing any pair back into a bool re-creates the defect
"""C019-UNIT-002 — four answers, and the count that keeps none of them silent.

#1598 specifies THREE answers: instantiated-and-reachable,
declared-but-not-instantiated, could-not-confirm. This test pins FOUR, and the
fourth is a RECORDED DEVIATION (see #1598 Entry 3 and Decision 8), not an
oversight — so it is asserted here rather than left to prose.

The three map cleanly onto the #1719/C013 vocabulary::

    instantiated and reachable      -> PASS
    declared but not instantiated   -> FAIL
    could not confirm               -> COULD_NOT_CHECK   (refuses)

A repo that registers NO journey map fits none of them, and that repo is atdd
itself. FAIL would assert atdd ought to be a Station Master, reversing #1618's
ruling. COULD_NOT_CHECK would be false: the check looked and DID establish the
absence, and ``GateVerdict.COULD_NOT_CHECK``'s own docstring reserves it for an
observation that could not be PERFORMED. ``NOT_APPLICABLE`` is the member C013
added for exactly "it looked; there is no obligation here".

WHAT STOPS THAT FOURTH ANSWER FROM BECOMING THE SILENT PASS #1598 PROHIBITS is
the last test in this file: the no-claim message must REPORT the counts. Without
that, NOT_APPLICABLE degrades into "nothing to see here" and the 16-trains /
2-interlockings gap goes quiet — which is the whole defect program #1734 exists
to remove. The assertion is the guard; the deviation is indefensible without it.

RED state: ``atdd.coach.gate.train_instantiation_check`` does not exist.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.decision import GateContext, GateVerdict

pytestmark = [pytest.mark.platform]

_ISSUE = 999019
_TRAIN = "0007-enforce-extension-conventions"


def _ctx(worktree: Path) -> GateContext:
    return GateContext(
        issue_number=_ISSUE, from_phase="SMOKE", to_phase="REFACTOR", worktree=worktree
    )


def test_a_recorded_dispatch_at_head_is_instantiated_and_reachable(tmp_path: Path):
    """C019-UNIT-002: PASS — the only answer that claims verification."""
    from atdd.coach.gate.train_instantiation_check import TrainInstantiationGateCheck
    from atdd.coach.gate.tests._c019_support import repo_with_dispatch

    worktree = repo_with_dispatch(tmp_path, train_id=_TRAIN)
    result = TrainInstantiationGateCheck().run(_ctx(worktree))

    assert result.verdict is GateVerdict.PASS
    assert result.passed is True
    assert _TRAIN in result.message, (
        "a PASS must name the train the dispatch actually routed to; 'something "
        "ran' is not evidence that THIS train ran"
    )


def test_a_registration_with_no_dispatch_is_declared_but_not_instantiated(tmp_path: Path):
    """C019-UNIT-002: FAIL — the registration is a CLAIM, never the answer.

    This is the state the passing ``bilateral_binding_complete`` fixture in the
    train-interlocking-enforcement extension is in RIGHT NOW: a JOURNEY_MAP
    literal parsed with ``ast`` and never executed. It satisfies
    ``declaration_to_station`` statically while being, at runtime, exactly this.
    It is the dead route table #1618 refused to create in atdd.
    """
    from atdd.coach.gate.train_instantiation_check import TrainInstantiationGateCheck
    from atdd.coach.gate.tests._c019_support import repo_with_registration_only

    worktree = repo_with_registration_only(tmp_path, train_id=_TRAIN)
    result = TrainInstantiationGateCheck().run(_ctx(worktree))

    assert result.verdict is GateVerdict.FAIL
    assert result.passed is False
    assert _TRAIN in result.message


@pytest.mark.parametrize("fault", ["unreadable_store", "unresolvable_target"])
def test_an_unmade_observation_is_could_not_check_and_says_what(tmp_path: Path, fault: str):
    """C019-UNIT-002: COULD_NOT_CHECK — and the message NAMES the thing.

    "A refusal an operator cannot act on is only marginally better than the
    vacuous pass it replaces" — ``GateCheckResult.could_not_check``'s own
    docstring. So naming what could not be observed is asserted, not hoped for.
    """
    from atdd.coach.gate.train_instantiation_check import TrainInstantiationGateCheck
    from atdd.coach.gate.tests._c019_support import repo_with_fault

    worktree, expected_subject = repo_with_fault(tmp_path, fault=fault)
    result = TrainInstantiationGateCheck().run(_ctx(worktree))

    assert result.verdict is GateVerdict.COULD_NOT_CHECK
    assert result.passed is False
    assert expected_subject in result.message, (
        f"the message must name what could not be observed ({expected_subject!r}); "
        f"got: {result.message!r}"
    )


def test_no_registration_is_not_applicable_and_reports_the_gap(tmp_path: Path):
    """C019-UNIT-002: the fourth answer — and the guard that keeps it honest.

    atdd's own answer. It must NOT be a silent pass: the message carries the
    declared-train count, the interlocking count and the zero registrations, so
    the 16-vs-2 gap is reported rather than shrugged off. Paying that gap down is
    #1578's job; reporting it is this gate's.
    """
    from atdd.coach.gate.train_instantiation_check import TrainInstantiationGateCheck
    from atdd.coach.gate.tests._c019_support import repo_with_no_registration

    worktree = repo_with_no_registration(tmp_path, trains=16, interlockings=2)
    result = TrainInstantiationGateCheck().run(_ctx(worktree))

    assert result.verdict is GateVerdict.NOT_APPLICABLE
    assert result.passed is True, "NOT_APPLICABLE proceeds — it does not refuse"

    for count in ("16", "2", "0"):
        assert count in result.message, (
            f"the no-claim message must report the counts (trains/interlockings/"
            f"registrations); {count!r} missing from: {result.message!r}"
        )


def test_the_declared_train_count_sums_the_nested_structure(tmp_path: Path):
    """C019-UNIT-002: 16, not the 5 a top-level len() returns.

    ``plan/_trains.yaml`` is a nested ``theme -> category -> [train]`` map. A
    naive ``len(yaml["trains"])`` counts THEMES and reads 5 — wrong by 11, and
    wrong in the flattering direction for a gate whose job is reporting the gap.
    """
    from atdd.coach.gate.train_instantiation_check import count_declared_trains
    from atdd.coach.gate.tests._c019_support import nested_trains_yaml

    plan = nested_trains_yaml(tmp_path, themes=5, trains=16)
    assert count_declared_trains(plan) == 16


def test_the_two_blocking_answers_stay_distinguishable(tmp_path: Path):
    """C019-UNIT-002: FAIL lands in failures, COULD_NOT_CHECK in unobservable.

    Identical in effect, distinct in reporting — the remedies differ completely.
    "Your declared train never ran" and "I could not read your store" send an
    operator to different places, and pooling them re-creates exactly the
    ambiguity C013 partitioned ``GateOutcome`` to remove.
    """
    from atdd.coach.gate.decision import evaluate_gate
    from atdd.coach.gate.train_instantiation_check import TrainInstantiationGateCheck
    from atdd.coach.gate.tests._c019_support import (
        repo_with_fault,
        repo_with_registration_only,
    )

    check = TrainInstantiationGateCheck()
    declared_only = check.run(_ctx(repo_with_registration_only(tmp_path / "a", train_id=_TRAIN)))
    unreadable, _ = repo_with_fault(tmp_path / "b", fault="unreadable_store")
    could_not = check.run(_ctx(unreadable))

    outcome = evaluate_gate([declared_only, could_not])

    assert outcome.proceed is False
    assert outcome.failures == (declared_only,)
    assert outcome.unobservable == (could_not,)
    assert len(outcome.blockers) == 2
