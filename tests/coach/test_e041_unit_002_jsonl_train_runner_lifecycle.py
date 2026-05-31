# URN: test:govern-lifecycle:extract-workflow-issue-runner-and-workflow-runner-protocol:E041-UNIT-002-jsonl-train-runner-lifecycle
# Acceptance: acc:govern-lifecycle:E041-UNIT-002-jsonl-train-runner-lifecycle
"""Unit test for E041-UNIT-002 (docs/coach-decomposition.md §4.7, §7.1).

``JsonlTrainRunner`` implements the Child-8 surface of the ``TrainRunner``
Protocol: ``start_issue`` creates a durable run and drives the issue via
``atdd.train.issue_runner.drive_single_issue``; ``status`` / ``cancel`` operate on
the persisted run; the Child-9 surface (``resume`` / ``run_wave``) is reserved
with ``NotImplementedError``.
"""
from __future__ import annotations

import pytest

from atdd.coach import core as coach_core
from atdd.train import issue_runner as issue_runner_mod
from atdd.train.persistence import JsonlPersistenceStore, load_conventions
from atdd.train.runner_iface import PolicyHandle, RunId
from atdd.train.runners.jsonl import JsonlTrainRunner

from tests.coach._e040_helpers import build_temp_repo


def _runner(tmp_path):
    build_temp_repo(tmp_path, issue_number=895, status="INIT")
    store = JsonlPersistenceStore(tmp_path)
    policy = PolicyHandle(coach_module=coach_core, conventions=load_conventions(tmp_path))
    runner = JsonlTrainRunner(
        persistence=store,
        runtime_dir=tmp_path / ".atdd" / "runtime",
    )
    return runner, policy, store


def test_start_issue_creates_run_and_drives_via_issue_runner(tmp_path, monkeypatch):
    runner, policy, store = _runner(tmp_path)

    calls: list[int] = []

    def _fake_drive(cfg, sm, runtime_dir, **kwargs):
        calls.append(sm.issue_number)
        return 0

    monkeypatch.setattr(issue_runner_mod, "drive_single_issue", _fake_drive)

    run_id = runner.start_issue(895, policy=policy)

    assert isinstance(run_id, str)  # RunId is an opaque str NewType
    run_dir = tmp_path / ".atdd" / "runtime" / "runs" / str(run_id)
    assert (run_dir / "events.jsonl").is_file()
    events = list(store.replay_events(RunId(run_id)))
    assert events and events[0].type == "RunStarted"
    assert calls == [895], "drive_single_issue must be invoked exactly once for the issue"


def test_status_reflects_persisted_run(tmp_path, monkeypatch):
    runner, policy, _ = _runner(tmp_path)
    monkeypatch.setattr(issue_runner_mod, "drive_single_issue", lambda *a, **k: 0)
    run_id = runner.start_issue(895, policy=policy)

    status = runner.status(run_id)
    assert status.run_id == run_id
    assert status.issue_number == 895
    assert status.state == "RUNNING"


def test_cancel_appends_runcancelled_and_marks_state(tmp_path, monkeypatch):
    runner, policy, store = _runner(tmp_path)
    monkeypatch.setattr(issue_runner_mod, "drive_single_issue", lambda *a, **k: 0)
    run_id = runner.start_issue(895, policy=policy)

    runner.cancel(run_id, reason="operator aborted")

    types = [e.type for e in store.replay_events(RunId(run_id))]
    assert "RunCancelled" in types
    assert runner.status(run_id).state == "CANCELLED"


def test_resume_and_run_wave_are_implemented_in_child_9(tmp_path, monkeypatch):
    """Child 9 (#896) lands ``resume`` + ``run_wave``; they no longer raise.

    (Child 8 reserved both with ``NotImplementedError``; this is the supersession
    point — thorough coverage lives in ``tests/train/test_jsonl_crash_recovery.py``
    and the wave-runner unit tests.)
    """
    runner, policy, store = _runner(tmp_path)
    monkeypatch.setattr(issue_runner_mod, "drive_single_issue", lambda *a, **k: 0)
    run_id = runner.start_issue(895, policy=policy)

    # resume replays the run and records a RunResumed continuation marker.
    runner.resume(run_id)
    types = [e.type for e in store.replay_events(RunId(run_id))]
    assert "RunResumed" in types

    # run_wave returns a typed WaveResult partitioning the issues it drove.
    result = runner.run_wave([895], concurrency=1)
    from atdd.train.types import WaveResult

    assert isinstance(result, WaveResult)
    assert result.failed_to_start == ()
