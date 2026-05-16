# URN: test:coach-wave-orchestration:within-wave-concurrency-and-pane-identity:E001-UNIT-001-concurrent-spawn-before-terminal
# Acceptance: acc:coach-wave-orchestration:E001-UNIT-001-concurrent-spawn-before-terminal
# WMBT: wmbt:coach-wave-orchestration:E001
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E001-UNIT-001 — every member of a single dependency-free wave begins driving
before any one of them reaches a terminal phase.

RED: ``_execute_cold_start`` currently loops ``for issue_num in wave`` calling
the blocking ``_drive_single_issue`` one issue at a time, so #B is never entered
until #A has returned a terminal result. This test pins the concurrent
behaviour — both members alive at once, each under its own coach-run id, and the
docstring reconciled with the wave plan it prints.
"""
from __future__ import annotations

import threading
import uuid

import pytest

from atdd.coach.commands import coach

pytestmark = [pytest.mark.platform]

ISSUE_A = 9001
ISSUE_B = 9002


def test_wave_members_drive_concurrently_before_terminal(tmp_path, monkeypatch):
    """Both wave members enter ``_drive_single_issue`` before either returns."""
    # build_plan -> None makes _execute_cold_start fall back to a single wave
    # holding every issue number: waves == [[ISSUE_A, ISSUE_B]].
    monkeypatch.setattr(coach, "build_plan", lambda nums: None)

    lock = threading.Lock()
    entered: list[int] = []
    active = {"now": 0, "peak": 0}
    # A barrier of 2 only releases once BOTH members have entered the driver.
    # Serial, blocking execution can never satisfy it — the first arrival waits
    # alone until the timeout, proving the members never overlapped.
    barrier = threading.Barrier(2, timeout=3)

    def fake_drive(cfg, sm, runtime_dir, *, _run_id_sink=None, **kwargs):
        with lock:
            entered.append(sm.issue_number)
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
        if _run_id_sink is not None:
            _run_id_sink.append(f"coach-run-{sm.issue_number}-{uuid.uuid4().hex[:8]}")
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        with lock:
            active["now"] -= 1
        return 0

    monkeypatch.setattr(coach, "_drive_single_issue", fake_drive)

    cfg = coach.Config(issue_numbers=[ISSUE_A, ISSUE_B])
    machines = [coach.initialize_state_machine(n) for n in (ISSUE_A, ISSUE_B)]
    run_ids: list[str] = []

    coach._execute_cold_start(cfg, machines, tmp_path, _run_id_sink=run_ids)

    # Both members were entered, and both were active inside the driver at the
    # same instant — impossible under the serial loop.
    assert set(entered) == {ISSUE_A, ISSUE_B}
    assert active["peak"] == 2, (
        f"expected both wave members driven concurrently; peak concurrent "
        f"depth was {active['peak']} (serial within-wave execution)"
    )
    # Each member is driven under its own distinct coach-run id.
    assert len(run_ids) == 2, run_ids
    assert len(set(run_ids)) == 2, f"coach-run ids not distinct: {run_ids}"
    # The docstring must no longer assert serial-only within-wave execution.
    doc = coach._execute_cold_start.__doc__ or ""
    assert "no parallel-within-wave" not in doc, (
        "_execute_cold_start docstring still claims 'no parallel-within-wave'"
    )
