# URN: test:coach-wave-orchestration:within-wave-concurrency-and-pane-identity:E001-INTEGRATION-001-between-wave-dependency-order-preserved
# Acceptance: acc:coach-wave-orchestration:E001-INTEGRATION-001-between-wave-dependency-order-preserved
# WMBT: wmbt:coach-wave-orchestration:E001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E001-INTEGRATION-001 — when a real inter-issue dependency exists,
``compute_waves`` ordering is honoured: the dependent issue runs strictly after
its dependency, and concurrency within a wave does not collapse the
between-wave sequencing.

#C declares a dependency on #A, so ``compute_waves`` emits wave 0 = [#A] and
wave 1 = [#C]. The concurrent driver runs each wave member off the calling
thread; the serial loop drives them inline on the main thread — that is the
RED discriminator alongside the preserved ordering.
"""
from __future__ import annotations

import threading
import time

import pytest

from atdd.coach.commands import coach

pytestmark = [pytest.mark.platform]

ISSUE_A = 9301
ISSUE_C = 9303


def test_between_wave_dependency_order_preserved(tmp_path, monkeypatch):
    """#C is entered only after #A is terminal; both waves run in order."""
    # #C depends on #A => two dependency-ordered single-member waves.
    monkeypatch.setattr(coach, "build_plan", lambda nums: {"plan": True})
    monkeypatch.setattr(coach, "compute_waves", lambda plan: [[ISSUE_A], [ISSUE_C]])

    lock = threading.Lock()
    starts: dict[int, float] = {}
    terminals: dict[int, float] = {}
    drive_order: list[int] = []
    on_main_thread: set[bool] = set()

    def fake_drive(cfg, sm, runtime_dir, **kwargs):
        n = sm.issue_number
        with lock:
            starts[n] = time.monotonic()
            drive_order.append(n)
            on_main_thread.add(threading.current_thread() is threading.main_thread())
        time.sleep(0.05)
        with lock:
            terminals[n] = time.monotonic()
        return 0

    monkeypatch.setattr(coach, "_drive_single_issue", fake_drive)

    cfg = coach.Config(issue_numbers=[ISSUE_A, ISSUE_C])
    machines = [coach.initialize_state_machine(n) for n in (ISSUE_A, ISSUE_C)]

    coach._execute_cold_start(cfg, machines, tmp_path)

    # Both members were driven, and #C waited for #A to reach terminal.
    assert set(drive_order) == {ISSUE_A, ISSUE_C}
    assert starts[ISSUE_C] >= terminals[ISSUE_A], (
        "#C was entered before its dependency #A reached a terminal state"
    )
    # Exactly two waves, executed in dependency order.
    assert drive_order == [ISSUE_A, ISSUE_C], (
        f"waves not executed in dependency order: {drive_order}"
    )
    # The concurrent driver runs each wave member off the calling thread;
    # the serial within-wave loop drives them inline on the main thread.
    assert on_main_thread == {False}, (
        "wave members were driven inline on the main thread (serial executor) "
        "rather than off-thread via the concurrent within-wave driver"
    )
