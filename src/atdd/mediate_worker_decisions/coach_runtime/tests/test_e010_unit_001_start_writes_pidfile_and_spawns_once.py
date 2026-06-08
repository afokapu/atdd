# URN: test:mediate-worker-decisions:coach-runtime:E010-UNIT-001-start-writes-pidfile-and-spawns-once
# Acceptance: acc:mediate-worker-decisions:E010-UNIT-001-start-writes-pidfile-and-spawns-once
# WMBT: wmbt:mediate-worker-decisions:E010
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E010-UNIT-001 — a first start writes the manager record and launches once.

`atdd coach start` for a workspace with no live managed daemon runs the gate,
launches the workspace-scoped feed_daemon exactly once (as a cmux surface), and
persists a manager record naming the daemon's own cmux workspace.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.coach_runtime.src.application.coach_runtime import (
    CoachRuntime,
)
from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
    ManagerRegistry,
)
from atdd.mediate_worker_decisions.coach_runtime.tests._helpers import (
    FakeLiveness,
    RecordingCloser,
    RecordingSpawner,
    StubGate,
    fake_argv,
)


def _runtime(root, spawner, liveness, gate):
    return CoachRuntime(
        registry=ManagerRegistry(root),
        spawner=spawner,
        liveness=liveness,
        closer=RecordingCloser(),
        gate=gate,
        daemon_argv=fake_argv,
    )


def test_first_start_spawns_once_and_writes_pidfile(tmp_path):
    root = tmp_path / "coach-runtime"
    spawner = RecordingSpawner(daemon_workspace="workspace:42")
    gate = StubGate()
    runtime = _runtime(root, spawner, FakeLiveness(), gate)

    daemon = runtime.start(
        "ws-1",
        lock_path=str(tmp_path / "feed.lock"),
        escalations_path=str(tmp_path / "escalations.jsonl"),
        verdicts_path=str(tmp_path / "verdicts.jsonl"),
    )

    assert len(spawner.calls) == 1  # launched exactly once
    assert "--workspace" in spawner.calls[0]
    assert "ws-1" in spawner.calls[0]
    assert gate.calls == 1  # ran the gate first

    reloaded = ManagerRegistry(root).load("ws-1")
    assert reloaded is not None
    assert reloaded.daemon_workspace == "workspace:42"
    assert daemon.daemon_workspace == "workspace:42"
