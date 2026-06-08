# URN: test:mediate-worker-decisions:coach-runtime:R003-UNIT-002-daemons-lists-live-and-stale
# Acceptance: acc:mediate-worker-decisions:R003-UNIT-002-daemons-lists-live-and-stale
# WMBT: wmbt:mediate-worker-decisions:R003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""R003-UNIT-002 — the daemons listing reports live vs stale per pidfile.

`atdd coach daemons` derives each managed daemon's status from a liveness probe:
a pidfile naming a live pid is reported running; one naming a dead pid is stale.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.coach_runtime.src.application.coach_runtime import (
    CoachRuntime,
)
from atdd.mediate_worker_decisions.coach_runtime.src.domain.managed_daemon import (
    STATUS_RUNNING,
    STATUS_STALE,
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


def _rec(ws, daemon_workspace, tmp_path):
    return ManagedDaemon(
        workspace_id=ws,
        daemon_workspace=daemon_workspace,
        lock_path=str(tmp_path / f"{ws}.lock"),
        escalations_path=str(tmp_path / f"{ws}.escalations.jsonl"),
        verdicts_path=str(tmp_path / f"{ws}.verdicts.jsonl"),
    )


def test_list_marks_live_and_stale(tmp_path):
    registry = ManagerRegistry(tmp_path / "coach-runtime")
    registry.save(_rec("ws-live", "workspace:111", tmp_path))
    registry.save(_rec("ws-dead", "workspace:222", tmp_path))
    runtime = CoachRuntime(
        registry=registry,
        spawner=RecordingSpawner(),
        # only ws-live's daemon surface still exists
        liveness=FakeLiveness(alive={"workspace:111"}),
        closer=RecordingCloser(),
        gate=StubGate(),
        daemon_argv=fake_argv,
    )

    listing = {d.workspace_id: d.status for d in runtime.list_daemons()}

    assert listing == {"ws-live": STATUS_RUNNING, "ws-dead": STATUS_STALE}
