# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""The smoke-execution attestation primitive (#1602) — record, read, and judge.

Two halves, tested apart because they fail apart:

* :func:`~atdd.state.evidence.evaluate_smoke_execution` is PURE over a sequence
  of runs, so every rejection clause is asserted directly rather than through a
  store. The parametrized table below is the specification: it names, for each
  historical false-green, the shape of record that must NOT satisfy the gate.
* :func:`~atdd.state.evidence.record_smoke_execution` /
  :func:`~atdd.state.evidence.smoke_executions` round-trip through a REAL
  migrated SQLite store (no mock), because the failure mode that matters — the
  foreign key refusing a row for a uid nothing owns — only exists in sqlite.

The negative control is deliberate and load-bearing: a verdict function that
rejected everything would satisfy every "must be rejected" case here and be
worthless, so ``test_a_real_passing_run_satisfies_the_verdict`` runs first in
spirit — without it the rest of this file proves nothing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.smoke_evidence import (
    CLAUSE_SMOKE_NOT_ATTESTED,
    CLAUSE_SMOKE_NOT_EXECUTED,
    CLAUSE_SMOKE_STALE_COMMIT,
    CLAUSE_SMOKE_ZERO_DURATION,
    SMOKE_EXECUTION_EVENT,
    SmokeAttestationError,
    SmokeRun,
    evaluate_smoke_execution,
    open_state_store,
    record_smoke_execution,
    smoke_executions,
)
from atdd.state.store import StateStore

pytestmark = [pytest.mark.platform]

UID = "smoke-execution-gate-wiring"
SHA = "a" * 40
OTHER_SHA = "b" * 40


def _run(**overrides) -> SmokeRun:
    """A run that DOES satisfy the verdict, unless a field is overridden."""
    base = dict(
        nodeid="tests/smoke/test_live.py::test_end_to_end",
        outcome="passed",
        duration_s=4.2,
        commit_sha=SHA,
        execution_kind="live_smoke",
    )
    base.update(overrides)
    return SmokeRun(**base)


# --------------------------------------------------------------------------- #
# The negative control — without this the rejection table below is meaningless #
# --------------------------------------------------------------------------- #


def test_a_real_passing_run_satisfies_the_verdict() -> None:
    """A live-smoke test that ran, passed, and took real time is enough."""
    verdict = evaluate_smoke_execution([_run()], head_sha=SHA)

    assert verdict.satisfied, verdict.detail
    assert verdict.clause is None
    assert "4.2" in verdict.detail, "the verdict must name the evidence it accepted"


# --------------------------------------------------------------------------- #
# The rejection table — one row per historical false-green                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "runs, clause, why",
    [
        ([], CLAUSE_SMOKE_NOT_ATTESTED, "nothing recorded at all"),
        (
            [_run(outcome="skipped")],
            CLAUSE_SMOKE_NOT_EXECUTED,
            "#1076: C010-SMOKE-001 'passed' by skipping; run for real it FAILED",
        ),
        (
            [_run(outcome="failed")],
            CLAUSE_SMOKE_NOT_EXECUTED,
            "a failing smoke run is not executed smoke",
        ),
        (
            [_run(outcome="skipped"), _run(outcome="failed")],
            CLAUSE_SMOKE_NOT_EXECUTED,
            "several runs, none of them passing",
        ),
        (
            [_run(duration_s=0.0)],
            CLAUSE_SMOKE_ZERO_DURATION,
            "a passing run that measured no time did not execute",
        ),
        (
            [_run(commit_sha=OTHER_SHA)],
            CLAUSE_SMOKE_STALE_COMMIT,
            "smoke ran, but against different code than the one being advanced",
        ),
        (
            [_run(commit_sha=None)],
            CLAUSE_SMOKE_STALE_COMMIT,
            "a run that did not record which code it exercised proves nothing about HEAD",
        ),
    ],
)
def test_degenerate_records_do_not_satisfy_the_verdict(runs, clause, why) -> None:
    verdict = evaluate_smoke_execution(runs, head_sha=SHA)

    assert not verdict.satisfied, f"{why} — must not satisfy the smoke-execution gate"
    assert verdict.clause == clause, f"{why} — wrong clause: {verdict.detail}"
    assert verdict.detail, "every rejection must name what is wrong"


def test_one_passing_run_among_skips_is_enough() -> None:
    """A suite where most smoke tests skipped but one really ran still counts.

    The gate asks whether smoke executed, not whether every smoke test did — and
    demanding the latter would make any partially-applicable suite unpassable.
    """
    verdict = evaluate_smoke_execution(
        [_run(outcome="skipped"), _run(), _run(outcome="skipped")], head_sha=SHA
    )

    assert verdict.satisfied, verdict.detail


def test_unresolvable_head_relaxes_only_the_staleness_clause() -> None:
    """``head_sha=None`` must not become a blanket pass.

    An environment that cannot resolve HEAD still has to prove execution; only
    the "is this the current code" question is unanswerable and so unasked.
    """
    assert evaluate_smoke_execution([_run(commit_sha=OTHER_SHA)], head_sha=None).satisfied

    for degenerate in ([], [_run(outcome="skipped")], [_run(duration_s=0.0)]):
        assert not evaluate_smoke_execution(degenerate, head_sha=None).satisfied, (
            "an unresolvable HEAD must not wave through a run that never executed"
        )


# --------------------------------------------------------------------------- #
# Store round-trip — against a real migrated SQLite store                     #
# --------------------------------------------------------------------------- #


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    """A real, migrated State Store holding one work item."""
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    conn = connect(db)
    state = StateStore(conn)
    state.objects.upsert(UID, "work_item", state="SMOKE")
    yield state
    conn.close()


def test_recorded_runs_read_back_intact(store: StateStore) -> None:
    record_smoke_execution(store, UID, _run(nodeid="a::b"))
    record_smoke_execution(store, UID, _run(nodeid="c::d", outcome="skipped", duration_s=0.0))

    runs = smoke_executions(store, UID)

    assert [r.nodeid for r in runs] == ["a::b", "c::d"], "append order must survive"
    assert [r.outcome for r in runs] == ["passed", "skipped"], (
        "a skip must be recorded as a skip — an absent skip is indistinguishable "
        "from a run that never happened (#1076)"
    )
    assert runs[0].commit_sha == SHA and runs[0].execution_kind == "live_smoke"
    assert evaluate_smoke_execution(runs, head_sha=SHA).satisfied


def test_attestation_is_scoped_to_its_work_item(store: StateStore) -> None:
    """One work item's smoke run must never satisfy another's transition."""
    store.objects.upsert("some-other-issue", "work_item", state="SMOKE")
    record_smoke_execution(store, "some-other-issue", _run())

    assert smoke_executions(store, UID) == []
    assert not evaluate_smoke_execution(smoke_executions(store, UID), head_sha=SHA).satisfied


def test_unrelated_events_on_the_same_uid_are_not_attestations(store: StateStore) -> None:
    """Only ``smoke_execution_attested`` events count — not any event at all."""
    store.events.append("version_bumped", object_uid=UID, payload={"outcome": "passed"})

    assert smoke_executions(store, UID) == []


def test_recording_against_an_unknown_work_item_raises(store: StateStore) -> None:
    """Loud, not silent: evidence filed under a uid nothing owns is unfindable."""
    with pytest.raises(SmokeAttestationError) as excinfo:
        record_smoke_execution(store, "no-such-work-item", _run())

    assert "no-such-work-item" in str(excinfo.value)


def test_a_malformed_payload_degrades_instead_of_crashing(store: StateStore) -> None:
    """A record written by a drifted producer must not take the reader down."""
    store.events.append(
        SMOKE_EXECUTION_EVENT, object_uid=UID,
        payload={"nodeid": "x::y", "outcome": "passed", "duration_s": "not-a-number"},
    )

    runs = smoke_executions(store, UID)

    assert len(runs) == 1
    assert runs[0].duration_s == 0.0, (
        "an unreadable duration must read as 'nothing executed', not as a pass"
    )
    assert not evaluate_smoke_execution(runs, head_sha=SHA).satisfied


def test_open_state_store_resolves_and_migrates(tmp_path: Path) -> None:
    """The convenience opener yields a usable store at the given control root."""
    with open_state_store(db_path=tmp_path / "state.sqlite") as state:
        state.objects.upsert(UID, "work_item")
        record_smoke_execution(state, UID, _run())

    with open_state_store(db_path=tmp_path / "state.sqlite") as state:
        assert len(smoke_executions(state, UID)) == 1, "the write must have persisted"
