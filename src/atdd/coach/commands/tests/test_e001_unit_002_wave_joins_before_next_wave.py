# URN: test:coach-wave-orchestration:within-wave-concurrency-and-pane-identity:E001-UNIT-002-wave-joins-before-next-wave
# Acceptance: acc:coach-wave-orchestration:E001-UNIT-002-wave-joins-before-next-wave
# WMBT: wmbt:coach-wave-orchestration:E001
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E001-UNIT-002 — ``_execute_cold_start`` does not start any issue of wave N+1
until every member of wave N has reached a terminal state.

The join property is only meaningful once wave members run concurrently, so
this test pins both: wave 0 = [#A, #B] driven in parallel, and #C (wave 1)
entered strictly after BOTH wave-0 members are terminal.
"""
from __future__ import annotations

import threading
import time

import pytest

from atdd.coach.commands import coach

pytestmark = [pytest.mark.platform]

ISSUE_A = 9101
ISSUE_B = 9102
ISSUE_C = 9103


def test_next_wave_waits_for_prior_wave_to_join(tmp_path, monkeypatch):
    """#C (wave 1) starts only after #A and #B (wave 0) both reach terminal."""
    monkeypatch.setattr(coach, "build_plan", lambda nums: {"plan": True})
    monkeypatch.setattr(
        coach, "compute_waves", lambda plan: [[ISSUE_A, ISSUE_B], [ISSUE_C]]
    )

    lock = threading.Lock()
    starts: dict[int, float] = {}
    terminals: dict[int, float] = {}
    active = {"now": 0, "peak": 0}
    # Wave-0 members synchronise on this barrier; wave-1's #C does not touch it.
    barrier = threading.Barrier(2, timeout=3)

    def fake_drive(cfg, sm, runtime_dir, **kwargs):
        n = sm.issue_number
        with lock:
            starts[n] = time.monotonic()
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
        if n in (ISSUE_A, ISSUE_B):
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
        else:
            time.sleep(0.05)
        with lock:
            active["now"] -= 1
            terminals[n] = time.monotonic()
        return 0

    monkeypatch.setattr(coach, "_drive_single_issue", fake_drive)

    cfg = coach.Config(issue_numbers=[ISSUE_A, ISSUE_B, ISSUE_C])
    machines = [coach.initialize_state_machine(n) for n in (ISSUE_A, ISSUE_B, ISSUE_C)]

    coach._execute_cold_start(cfg, machines, tmp_path)

    # Wave 0 ran concurrently...
    assert active["peak"] == 2, (
        f"wave-0 members were not driven concurrently; peak depth "
        f"{active['peak']}"
    )
    # ...and #C did not start until BOTH wave-0 members had reached terminal.
    assert starts[ISSUE_C] >= terminals[ISSUE_A], (
        "#C entered before #A reached a terminal state"
    )
    assert starts[ISSUE_C] >= terminals[ISSUE_B], (
        "#C entered before #B reached a terminal state"
    )
