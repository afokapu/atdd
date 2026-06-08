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
    def spawn(self, argv: List[str], *, log_path: Optional[str] = None) -> int:
        """Launch the feed_daemon CLI detached. Returns the child pid.

        ``log_path`` is a durable per-workspace sink for the detached daemon's
        stdout/stderr (so a runtime failure leaves a trace); when omitted the
        output is discarded. The autonomous coach always passes one — a daemon
        spawned to ``/dev/null`` is unobservable (WMBT M004).
        """


class LivenessProbe(Protocol):
    def is_alive(self, pid: int) -> bool:
        """True when a process with `pid` is currently live."""


class Signaller(Protocol):
    def signal(self, pid: int, sig: int) -> None:
        """Send signal `sig` to `pid`."""


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
