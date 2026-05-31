# URN: test:govern-lifecycle:extract-workflow-wave-runner-and-atdd-resume-cli:E042-UNIT-001-run-wave-concurrency-and-wave-result
# Acceptance: acc:govern-lifecycle:E042-UNIT-001-run-wave-concurrency-and-wave-result
"""Unit test for E042-UNIT-001 (docs/coach-decomposition.md §7.1, §7.4, §13.9).

``JsonlTrainRunner.run_wave`` resolves the dependency-ordered wave plan, drives
each wave's members concurrently bounded by ``train.concurrency.max_parallel_issues``,
and returns a typed ``WaveResult``; the concurrency cap itself lives in the pure
``atdd.train.wave_runner.drive_wave_concurrently`` helper.
"""
from __future__ import annotations

import threading
import time

from atdd.coach import core as coach_core
from atdd.train import issue_runner as issue_runner_mod
from atdd.train import wave_runner
from atdd.train.persistence import JsonlPersistenceStore, load_conventions
from atdd.train.runner_iface import PolicyHandle
from atdd.train.runners.jsonl import JsonlTrainRunner
from atdd.train.types import WaveResult

from tests.coach._e040_helpers import build_temp_repo


def _runner(tmp_path):
    build_temp_repo(tmp_path, issue_number=895, status="INIT")
    store = JsonlPersistenceStore(tmp_path)
    policy = PolicyHandle(coach_module=coach_core, conventions=load_conventions(tmp_path))
    runner = JsonlTrainRunner(
        persistence=store, runtime_dir=tmp_path / ".atdd" / "runtime"
    )
    runner.bind_policy(policy)
    return runner, policy, store


def test_run_wave_returns_wave_result_partitioning_issues(tmp_path, monkeypatch):
    runner, _policy, _store = _runner(tmp_path)
    monkeypatch.setattr(issue_runner_mod, "drive_single_issue", lambda *a, **k: 0)

    result = runner.run_wave([895], concurrency=1)

    assert isinstance(result, WaveResult)
    assert len(result.started) == 1
    assert result.blocked == ()
    assert result.failed_to_start == ()


def test_run_wave_captures_failed_to_start_without_aborting(tmp_path, monkeypatch):
    runner, _policy, _store = _runner(tmp_path)

    def _boom(*a, **k):
        raise RuntimeError("spawn exploded")

    monkeypatch.setattr(issue_runner_mod, "drive_single_issue", _boom)

    result = runner.run_wave([895], concurrency=1)

    assert result.started == ()
    assert len(result.failed_to_start) == 1
    issue_num, reason = result.failed_to_start[0]
    assert issue_num == 895
    assert "spawn exploded" in reason


def test_drive_wave_concurrently_honors_max_parallel():
    """The concurrency cap admits at most max_parallel workers at once."""
    peak = 0
    current = 0
    lock = threading.Lock()

    def _work(_issue: int) -> int:
        nonlocal peak, current
        with lock:
            current += 1
            peak = max(peak, current)
        time.sleep(0.02)
        with lock:
            current -= 1
        return 0

    wave = list(range(6))
    results = wave_runner.drive_wave_concurrently(wave, _work, max_parallel=2)

    assert set(results) == set(wave), "every member must be joined before returning"
    assert peak <= 2, f"max_parallel=2 must cap concurrency, saw peak {peak}"


def test_drive_wave_concurrently_unbounded_when_cap_none():
    """With no cap, all members may run concurrently (the prior behavior)."""
    started = threading.Barrier(4, timeout=5)

    def _work(_issue: int) -> int:
        # If fewer than 4 run concurrently this barrier times out → test fails.
        started.wait()
        return 0

    results = wave_runner.drive_wave_concurrently(list(range(4)), _work, max_parallel=None)
    assert set(results) == {0, 1, 2, 3}
