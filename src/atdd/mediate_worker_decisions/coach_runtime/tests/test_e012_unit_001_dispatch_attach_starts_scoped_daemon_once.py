# URN: test:mediate-worker-decisions:coach-runtime:E012-UNIT-001-dispatch-attach-starts-scoped-daemon-once
# Acceptance: acc:mediate-worker-decisions:E012-UNIT-001-dispatch-attach-starts-scoped-daemon-once
# WMBT: wmbt:mediate-worker-decisions:E012
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E012-UNIT-001 — the dispatch attach starts the scoped daemon exactly once.

attach_worker_daemon resolves the spawned worker surface to its OWN cmux
workspace and starts the workspace-scoped feed_daemon there exactly once — scoped
to the worker's workspace, not the coach's selected workspace.
"""
from __future__ import annotations

from typing import List, Optional

from atdd.mediate_worker_decisions.coach_runtime.src.domain.managed_daemon import (
    ManagedDaemon,
)
from atdd.mediate_worker_decisions.coach_runtime.src.presentation.attach_worker_daemon import (
    attach_worker_daemon,
)


class _FakeBackend:
    def __init__(self, workspace_id: str) -> None:
        self._workspace_id = workspace_id
        self.resolved: List[str] = []

    def surface_workspace(self, surface_ref: str) -> str:
        self.resolved.append(surface_ref)
        return self._workspace_id


class _RecordingRuntime:
    def __init__(self) -> None:
        self.started: List[dict] = []

    def start(self, workspace_id, *, lock_path, escalations_path, verdicts_path, run_gate=True):
        self.started.append({"workspace_id": workspace_id, "run_gate": run_gate})
        return ManagedDaemon(
            workspace_id=workspace_id,
            daemon_workspace="workspace:99",
            lock_path=lock_path,
            escalations_path=escalations_path,
            verdicts_path=verdicts_path,
        )


def test_attach_starts_scoped_to_worker_workspace_once(tmp_path):
    backend = _FakeBackend("workspace:7")
    runtime = _RecordingRuntime()

    attach_worker_daemon(
        backend, "surface:3", repo_cwd=tmp_path, runtime=runtime
    )

    assert len(runtime.started) == 1  # started exactly once
    assert runtime.started[0]["workspace_id"] == "workspace:7"  # the WORKER's ws
    assert backend.resolved == ["surface:3"]  # resolved from the spawned surface
    assert runtime.started[0]["run_gate"] is False  # dispatch already gated
