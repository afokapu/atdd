"""Application ports for the coach runtime (typing.Protocol seams).

Every cmux/process/clock specific is injected through one of these so the
use cases stay pure and unit-testable. The feed_daemon decide/escalate brain
is NOT a port here — `atdd coach start` reuses it wholesale by spawning the
feed_daemon CLI as a subprocess (DaemonSpawner).
"""
from __future__ import annotations

from typing import List, Optional, Protocol

from atdd.mediate_worker_decisions.coach_runtime.src.domain.managed_daemon import (
    ManagedDaemon,
)


class GateRunner(Protocol):
    def run(self) -> int:
        """Run `atdd gate` (preflight). Returns the gate's exit code."""


class DaemonSpawner(Protocol):
    def spawn(
        self, argv: List[str], *, name: str, log_path: Optional[str] = None
    ) -> str:
        """Launch the feed_daemon as a headless cmux SURFACE; return its workspace ref.

        The daemon runs INSIDE a cmux surface (``cmux new-workspace --focus false
        --command``) so it is a socket-recognized process — NOT a detached/orphaned
        subprocess, whose every ``cmux rpc`` broken-pipes (WMBT M005, #1007). ``name``
        names the daemon's surface; ``log_path`` is a durable per-workspace sink for
        the daemon's stdout/stderr (the surface command redirects to it) so a runtime
        failure leaves a trace (WMBT M004). Returns the daemon's own cmux workspace ref.
        """


class LivenessProbe(Protocol):
    def is_alive(self, daemon_workspace: str) -> bool:
        """True when the daemon's cmux workspace still exists (the surface is up)."""


class WorkspaceCloser(Protocol):
    def close(self, daemon_workspace: str) -> None:
        """Close the daemon's cmux workspace (``cmux close-workspace``)."""


class ManagerRegistryPort(Protocol):
    def save(self, daemon: ManagedDaemon) -> None: ...
    def load(self, workspace_id: str) -> Optional[ManagedDaemon]: ...
    def load_all(self) -> List[ManagedDaemon]: ...
    def remove(self, workspace_id: str) -> None: ...


class EscalationReader(Protocol):
    def read_all(self) -> List[dict]:
        """Return every escalation record appended to the ledger so far."""


class CursorStore(Protocol):
    def load(self) -> int: ...
    def save(self, cursor: int) -> None: ...


class Sleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


class StopSignal(Protocol):
    def is_set(self) -> bool: ...
