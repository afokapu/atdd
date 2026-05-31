# URN: test:govern-lifecycle:extract-workflow-wave-runner-and-atdd-resume-cli:E042-UNIT-002-jsonl-resume-replays-frozen-conventions
# Acceptance: acc:govern-lifecycle:E042-UNIT-002-jsonl-resume-replays-frozen-conventions
"""Unit test for E042-UNIT-002 (docs/coach-decomposition.md §6.3, §13.9).

``JsonlTrainRunner.resume`` implements the §6.3 replay-and-continue contract:
load the FROZEN conventions snapshot, replay events to reconstruct ``RunState``,
re-materialize evidence, recompute the decision via ``coach.core.next_transition``,
and append a ``RunResumed`` continuation + the recomputed decision — without
advancing the phase or re-dispatching. A recorded conventions-hash that disagrees
with the frozen snapshot raises rather than replaying non-deterministically.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach import core as coach_core
from atdd.coach.core.types import Phase
from atdd.train.events import SCHEMA_VERSION
from atdd.train.persistence import (
    JsonlPersistenceStore,
    load_conventions,
    load_conventions_for_run,
)
from atdd.train.runner_iface import PolicyHandle
from atdd.train.runners.jsonl import JsonlTrainRunner
from atdd.train.types import RunId, TrainEvent

from tests.coach._e040_helpers import build_temp_repo

ISSUE = 880


class _HermeticGitHub:
    def read_phase(self, issue: int):
        return None

    def read_pr_state(self, issue: int):
        return None

    def read_ci_state(self, issue: int) -> str:
        return "success"


def _store(repo_root: Path) -> JsonlPersistenceStore:
    return JsonlPersistenceStore(repo_root, github=_HermeticGitHub())


def _seed_run(tmp_path: Path) -> RunId:
    build_temp_repo(tmp_path, issue_number=ISSUE, status="GREEN")
    store = _store(tmp_path)
    run_id = store.create_run(ISSUE, conventions=load_conventions(tmp_path))
    store.append_event(
        run_id,
        TrainEvent(
            schema_version=SCHEMA_VERSION, ts="", run_id=run_id, issue_number=ISSUE,
            type="PhaseAdvanced",
            payload={"from_phase": "RED", "to_phase": "GREEN", "commit_sha": ""}, seq=0,
        ),
    )
    return run_id


def test_resume_appends_runresumed_and_recomputed_decision(tmp_path):
    run_id = _seed_run(tmp_path)
    run_dir = tmp_path / ".atdd" / "runtime" / "runs" / str(run_id)

    runner = JsonlTrainRunner(persistence=_store(tmp_path), runtime_dir=tmp_path / ".atdd" / "runtime")
    runner.resume(run_id)

    events = list(_store(tmp_path).replay_events(run_id))
    types = [e.type for e in events]
    assert "RunResumed" in types and "DecisionMade" in types

    resumed = next(e for e in events if e.type == "RunResumed")
    assert "from_event_seq" in resumed.payload

    # The recorded decision equals coach-core's decision over the FROZEN snapshot.
    frozen = load_conventions_for_run(run_dir)
    expected = coach_core.next_transition(_store(tmp_path).materialize_evidence(ISSUE), frozen)
    assert _store(tmp_path).load_run(run_id).decisions[-1] == expected


def test_resume_does_not_advance_phase(tmp_path):
    run_id = _seed_run(tmp_path)
    before = sum(1 for e in _store(tmp_path).replay_events(run_id) if e.type == "PhaseAdvanced")

    JsonlTrainRunner(
        persistence=_store(tmp_path), runtime_dir=tmp_path / ".atdd" / "runtime"
    ).resume(run_id)

    after = sum(1 for e in _store(tmp_path).replay_events(run_id) if e.type == "PhaseAdvanced")
    assert after == before
    assert _store(tmp_path).load_run(run_id).current_phase == Phase.GREEN


def test_resume_raises_on_conventions_snapshot_drift(tmp_path, monkeypatch):
    run_id = _seed_run(tmp_path)
    runner = JsonlTrainRunner(
        persistence=_store(tmp_path), runtime_dir=tmp_path / ".atdd" / "runtime"
    )

    # Force the reconstructed state to report a hash that disagrees with the
    # frozen snapshot — replay would not be deterministic, so resume must refuse.
    real_load_run = runner.persistence.load_run

    def _drifted(rid):
        state = real_load_run(rid)
        return state.__class__(
            run_id=state.run_id,
            issue_number=state.issue_number,
            current_phase=state.current_phase,
            conventions_hash="deadbeef-not-the-frozen-hash",
            decisions=state.decisions,
            last_event_seq=state.last_event_seq,
        )

    monkeypatch.setattr(runner.persistence, "load_run", _drifted)

    with pytest.raises(RuntimeError, match="drift"):
        runner.resume(run_id)
