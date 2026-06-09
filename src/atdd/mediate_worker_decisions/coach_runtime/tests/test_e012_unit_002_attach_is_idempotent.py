# URN: test:mediate-worker-decisions:coach-runtime:E012-UNIT-002-attach-is-idempotent
# Acceptance: acc:mediate-worker-decisions:E012-UNIT-002-attach-is-idempotent
# WMBT: wmbt:mediate-worker-decisions:E012
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E012-UNIT-002 — a second attach for a live worker workspace is a no-op.

Attaching to a worker whose workspace already has a LIVE managed daemon performs
no second spawn (never two daemons on one Feed) and returns the existing record.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.coach_runtime.composition import build_coach_runtime
from atdd.mediate_worker_decisions.coach_runtime.src.domain.managed_daemon import (
    ManagedDaemon,
)
from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
    ManagerRegistry,
)
from atdd.mediate_worker_decisions.coach_runtime.src.presentation.attach_worker_daemon import (
    attach_worker_daemon,
)
from atdd.mediate_worker_decisions.coach_runtime.tests._helpers import (
    FakeLiveness,
    RecordingCloser,
    RecordingSpawner,
    StubGate,
)


class _FakeBackend:
    def __init__(self, workspace_id: str) -> None:
        self._workspace_id = workspace_id

    def surface_workspace(self, surface_ref: str) -> str:
        return self._workspace_id


def test_second_attach_does_not_respawn(tmp_path):
    root = tmp_path / "coach-runtime"
    registry = ManagerRegistry(root)
    # A live managed daemon already watches the worker's workspace.
    registry.save(
        ManagedDaemon(
            workspace_id="workspace:7",
            daemon_workspace="workspace:42",
            lock_path=str(tmp_path / "f.lock"),
            escalations_path=str(tmp_path / "e.jsonl"),
            verdicts_path=str(tmp_path / "v.jsonl"),
        )
    )
    spawner = RecordingSpawner(daemon_workspace="workspace:99")
    runtime = build_coach_runtime(
        registry=registry,
        spawner=spawner,
        liveness=FakeLiveness(alive={"workspace:42"}),
        closer=RecordingCloser(),
        gate=StubGate(),
    )

    result = attach_worker_daemon(
        _FakeBackend("workspace:7"), "surface:5", repo_cwd=tmp_path, runtime=runtime
    )

    assert spawner.calls == []  # no second daemon spawned
    assert result is not None
    assert result.daemon_workspace == "workspace:42"  # existing record returned
