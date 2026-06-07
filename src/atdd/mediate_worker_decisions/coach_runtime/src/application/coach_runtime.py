"""Coach-runtime use cases (E010 start, L006 wait_next, R003 stop/list).

The use case owns the autonomous-loop lifecycle but none of its mechanism:
spawning, signalling, liveness, ledger reads, and the clock are all injected
ports. `start` is idempotent (a live managed daemon for the workspace is never
re-spawned); `wait_next` emits exactly one unhandled escalation past the cursor
then returns; `stop`/`list_daemons` operate over the manager registry.

Skeleton: bodies land in GREEN.
"""
from __future__ import annotations

import signal as _signal
from typing import List, Optional, Tuple

from atdd.mediate_worker_decisions.coach_runtime.src.application.ports import (
    CursorStore,
    DaemonSpawner,
    EscalationReader,
    GateRunner,
    LivenessProbe,
    ManagerRegistryPort,
    Signaller,
    Sleeper,
    StopSignal,
)
from atdd.mediate_worker_decisions.coach_runtime.src.domain.managed_daemon import (
    ManagedDaemon,
)


class CoachRuntime:
    def __init__(
        self,
        *,
        registry: ManagerRegistryPort,
        spawner: DaemonSpawner,
        liveness: LivenessProbe,
        signaller: Signaller,
        gate: Optional[GateRunner] = None,
        daemon_argv,
    ) -> None:
        self._registry = registry
        self._spawner = spawner
        self._liveness = liveness
        self._signaller = signaller
        self._gate = gate
        # daemon_argv: callable(ManagedDaemon-like paths) -> List[str]
        self._daemon_argv = daemon_argv

    def start(
        self,
        workspace_id: str,
        *,
        lock_path: str,
        escalations_path: str,
        verdicts_path: str,
        run_gate: bool = True,
    ) -> ManagedDaemon:
        raise NotImplementedError("GREEN")

    def wait_next(
        self,
        *,
        reader: EscalationReader,
        cursor_store: CursorStore,
        sleeper: Sleeper,
        stop: StopSignal,
        poll_interval: float = 1.0,
    ) -> Optional[dict]:
        raise NotImplementedError("GREEN")

    def stop(self, workspace_id: Optional[str] = None) -> List[ManagedDaemon]:
        raise NotImplementedError("GREEN")

    def list_daemons(self) -> List[ManagedDaemon]:
        raise NotImplementedError("GREEN")
