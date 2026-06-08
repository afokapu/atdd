# URN: test:mediate-worker-decisions:coach-runtime:M004-UNIT-001-start-passes-durable-log-path-to-spawner
# Acceptance: acc:mediate-worker-decisions:M004-UNIT-001-start-passes-durable-log-path-to-spawner
# WMBT: wmbt:mediate-worker-decisions:M004
# Phase: RED
# Layer: application
# Assertion: behavioral
"""M004-UNIT-001 — start hands the spawner a durable per-workspace log path.

`atdd coach start` must launch the managed daemon with its stdout/stderr directed to a
durable per-workspace ``daemon.log`` (so a runtime failure leaves a trace), NOT to
``/dev/null``. The use case proves this by passing the spawner a non-empty ``log_path``
whose basename is ``daemon.log`` and which sits beside the workspace's ledgers/lock.
"""
from __future__ import annotations

from pathlib import Path

from atdd.mediate_worker_decisions.coach_runtime.src.application.coach_runtime import (
    CoachRuntime,
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


def test_start_passes_durable_log_path_to_spawner(tmp_path):
    root = tmp_path / "coach-runtime"
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    spawner = RecordingSpawner(pid=4242)
    runtime = CoachRuntime(
        registry=ManagerRegistry(root),
        spawner=spawner,
        liveness=FakeLiveness(),
        signaller=RecordingSignaller(),
        gate=StubGate(),
        daemon_argv=fake_argv,
    )

    runtime.start(
        "ws-1",
        lock_path=str(ws_dir / "feed-daemon.lock"),
        escalations_path=str(ws_dir / "escalations.jsonl"),
        verdicts_path=str(ws_dir / "verdicts.jsonl"),
    )

    assert len(spawner.log_paths) == 1
    log_path = spawner.log_paths[0]
    assert log_path, "start did not pass a durable log_path (would spawn to /dev/null)"
    assert Path(log_path).name == "daemon.log"
    # beside the workspace's other runtime artifacts, not /dev/null
    assert Path(log_path).parent == ws_dir
