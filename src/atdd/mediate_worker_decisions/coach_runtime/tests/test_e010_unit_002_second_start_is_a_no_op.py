# URN: test:mediate-worker-decisions:coach-runtime:E010-UNIT-002-second-start-is-a-no-op
# Acceptance: acc:mediate-worker-decisions:E010-UNIT-002-second-start-is-a-no-op
# WMBT: wmbt:mediate-worker-decisions:E010
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E010-UNIT-002 — a second start for a live workspace is a no-op.

When a manager pidfile already records a LIVE daemon for the workspace, a second
`atdd coach start` must not spawn a second daemon and must leave the pidfile
unchanged (never two daemons deciding the same Feed).
"""
from __future__ import annotations

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
    RecordingCloser,
    RecordingSpawner,
    StubGate,
    fake_argv,
)


def test_second_start_does_not_spawn_when_live(tmp_path):
    root = tmp_path / "coach-runtime"
    registry = ManagerRegistry(root)
    registry.save(
        ManagedDaemon(
            workspace_id="ws-1",
            daemon_workspace="workspace:42",
            lock_path=str(tmp_path / "feed.lock"),
            escalations_path=str(tmp_path / "escalations.jsonl"),
            verdicts_path=str(tmp_path / "verdicts.jsonl"),
        )
    )
    spawner = RecordingSpawner(daemon_workspace="workspace:99")
    runtime = CoachRuntime(
        registry=registry,
        spawner=spawner,
        # the recorded daemon's surface still exists
        liveness=FakeLiveness(alive={"workspace:42"}),
        closer=RecordingCloser(),
        gate=StubGate(),
        daemon_argv=fake_argv,
    )

    result = runtime.start(
        "ws-1",
        lock_path=str(tmp_path / "feed.lock"),
        escalations_path=str(tmp_path / "escalations.jsonl"),
        verdicts_path=str(tmp_path / "verdicts.jsonl"),
    )

    assert len(spawner.calls) == 0  # no second launch
    assert result.daemon_workspace == "workspace:42"  # returned the existing daemon
    # manager record unchanged
    assert ManagerRegistry(root).load("ws-1").daemon_workspace == "workspace:42"
