# URN: test:mediate-worker-decisions:coach-runtime:R003-UNIT-001-stop-signals-pid-and-clears-pidfile
# Acceptance: acc:mediate-worker-decisions:R003-UNIT-001-stop-signals-pid-and-clears-pidfile
# WMBT: wmbt:mediate-worker-decisions:R003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""R003-UNIT-001 — stop signals the recorded pid and removes the pidfile.

`atdd coach stop` for a workspace with a live managed daemon sends a terminating
signal to the recorded pid and removes the manager pidfile, so a subsequent list
reports no live managed daemon.
"""
from __future__ import annotations

import signal

from atdd.mediate_worker_decisions.coach_runtime.src.application.coach_runtime import (
    CoachRuntime,
)
from atdd.mediate_worker_decisions.coach_runtime.src.domain.managed_daemon import (
    ManagedDaemon,
)
from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
    ManagerRegistry,
)
from atdd.mediate_worker_decisions.coach_runtime.tests._helpers import (
    FakeLiveness,
    RecordingSignaller,
    RecordingSpawner,
    StubGate,
    fake_argv,
)


def test_stop_signals_and_clears(tmp_path):
    root = tmp_path / "coach-runtime"
    registry = ManagerRegistry(root)
    registry.save(
        ManagedDaemon(
            workspace_id="ws-1",
            pid=999,
            lock_path=str(tmp_path / "feed.lock"),
            escalations_path=str(tmp_path / "escalations.jsonl"),
            verdicts_path=str(tmp_path / "verdicts.jsonl"),
        )
    )
    signaller = RecordingSignaller()
    runtime = CoachRuntime(
        registry=registry,
        spawner=RecordingSpawner(),
        liveness=FakeLiveness(alive={999}),
        signaller=signaller,
        gate=StubGate(),
        daemon_argv=fake_argv,
    )

    stopped = runtime.stop("ws-1")

    assert [d.workspace_id for d in stopped] == ["ws-1"]
    assert signaller.calls == [(999, signal.SIGTERM)]
    assert ManagerRegistry(root).load("ws-1") is None  # pidfile removed
    assert runtime.list_daemons() == []  # nothing managed afterward
