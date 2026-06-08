"""Coach-runtime use cases (E010 start, L006 wait_next, R003 stop/list).

The use case owns the autonomous-loop lifecycle but none of its mechanism:
spawning, signalling, liveness, ledger reads, and the clock are all injected
ports. `start` is idempotent (a live managed daemon for the workspace is never
re-spawned); `wait_next` emits exactly one unhandled escalation past the cursor
then returns; `stop`/`list_daemons` operate over the manager registry.

Skeleton: bodies land in GREEN.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from atdd.mediate_worker_decisions.coach_runtime.src.application.ports import (
    CursorStore,
    DaemonSpawner,
    EscalationReader,
    GateRunner,
    LivenessProbe,
    ManagerRegistryPort,
    Sleeper,
    StopSignal,
    WorkspaceCloser,
)
from atdd.mediate_worker_decisions.coach_runtime.src.domain.cursor import (
    next_escalation_after,
)
from atdd.mediate_worker_decisions.coach_runtime.src.domain.managed_daemon import (
    STATUS_RUNNING,
    STATUS_STALE,
    ManagedDaemon,
)

_DAEMON_WORKSPACE_PREFIX = "atdd-coach-daemon-"


def _default_daemon_name(workspace_id: str) -> str:
    """The cmux workspace title for the daemon watching ``workspace_id``."""
    return f"{_DAEMON_WORKSPACE_PREFIX}{workspace_id}"


class CoachRuntime:
    def __init__(
        self,
        *,
        registry: ManagerRegistryPort,
        spawner: DaemonSpawner,
        liveness: LivenessProbe,
        closer: WorkspaceCloser,
        gate: Optional[GateRunner] = None,
        daemon_argv,
        daemon_name: Optional[object] = None,
    ) -> None:
        self._registry = registry
        self._spawner = spawner
        self._liveness = liveness
        self._closer = closer
        self._gate = gate
        # daemon_argv: callable(ManagedDaemon-like paths) -> List[str]
        self._daemon_argv = daemon_argv
        # daemon_name: callable(workspace_id) -> str naming the daemon's own surface.
        self._daemon_name = daemon_name or _default_daemon_name

    def start(
        self,
        workspace_id: str,
        *,
        lock_path: str,
        escalations_path: str,
        verdicts_path: str,
        run_gate: bool = True,
    ) -> ManagedDaemon:
        """Idempotently launch the workspace-scoped feed_daemon.

        A live managed daemon for the workspace is returned unchanged (no second
        spawn — never two daemons on one Feed). Otherwise the gate runs, the
        feed_daemon CLI is spawned, and the manager pidfile is persisted.
        """
        existing = self._registry.load(workspace_id)
        if existing is not None and self._liveness.is_alive(existing.daemon_workspace):
            return existing  # no-op — already running

        if run_gate and self._gate is not None:
            self._gate.run()

        argv = self._daemon_argv(
            workspace_id=workspace_id,
            lock_path=lock_path,
            escalations_path=escalations_path,
            verdicts_path=verdicts_path,
        )
        # Launch the daemon INSIDE a headless cmux surface so it is a socket-recognized
        # process (#1007 / WMBT M005) — never an orphaned detached subprocess whose
        # cmux rpc broken-pipes. Its stdout/stderr are redirected to a durable
        # per-workspace daemon.log (beside its ledgers/lock), never /dev/null, so a
        # runtime failure leaves a diagnosable trace (WMBT M004).
        log_path = str(Path(lock_path).parent / "daemon.log")
        daemon_workspace = self._spawner.spawn(
            argv, name=self._daemon_name(workspace_id), log_path=log_path
        )
        daemon = ManagedDaemon(
            workspace_id=workspace_id,
            daemon_workspace=daemon_workspace,
            lock_path=lock_path,
            escalations_path=escalations_path,
            verdicts_path=verdicts_path,
        )
        self._registry.save(daemon)
        return daemon

    def wait_next(
        self,
        *,
        reader: EscalationReader,
        cursor_store: CursorStore,
        sleeper: Sleeper,
        stop: StopSignal,
        poll_interval: float = 1.0,
    ) -> Optional[dict]:
        """Block until the next unhandled escalation past the cursor, emit it, exit.

        Returns exactly one record (and persists the advanced cursor) so a
        handled escalation is never re-emitted. Returns ``None`` when ``stop``
        fires before any new escalation appears.
        """
        record: Optional[dict] = None
        advanced = 0
        while not stop.is_set():
            records = reader.read_all()
            cursor = cursor_store.load()
            record, advanced = next_escalation_after(records, cursor)
            if record is not None:
                break
            sleeper.sleep(poll_interval)
        if record is None:
            return None
        # The cursor advances exactly once, outside the poll loop — emitting one
        # record per invocation is the loop contract, so this is never an N+1.
        cursor_store.save(advanced)
        return record

    def stop(self, workspace_id: Optional[str] = None) -> List[ManagedDaemon]:
        """Close the daemon's cmux surface + deregister; idempotent on dead ones."""
        targets = (
            [d for d in [self._registry.load(workspace_id)] if d is not None]
            if workspace_id is not None
            else self._registry.load_all()
        )
        for daemon in targets:
            if self._liveness.is_alive(daemon.daemon_workspace):
                self._closer.close(daemon.daemon_workspace)
            self._registry.remove(daemon.workspace_id)
        return targets

    def list_daemons(self) -> List[ManagedDaemon]:
        """Every managed daemon with a derived running|stale status.

        Liveness is whether the daemon's own cmux surface workspace still exists.
        """
        out: List[ManagedDaemon] = []
        for daemon in self._registry.load_all():
            status = (
                STATUS_RUNNING
                if self._liveness.is_alive(daemon.daemon_workspace)
                else STATUS_STALE
            )
            out.append(daemon.with_status(status))
        return out
