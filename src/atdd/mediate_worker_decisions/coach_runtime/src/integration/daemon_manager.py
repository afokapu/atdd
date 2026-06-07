"""Process + pidfile mechanism for the coach runtime (integration).

``ManagerRegistry`` persists one ``manager.json`` per workspace under a runtime
root, so `start` is idempotent across invocations and `stop`/`daemons` can find
exactly what was launched. ``SubprocessDaemonSpawner`` launches the existing
feed_daemon CLI detached (reuse — never a reimplementation). ``OsLivenessProbe``
and ``OsSignaller`` wrap ``os.kill``. ``build_feed_daemon_argv`` renders the
launch argv as a pure function.

Skeleton: bodies land in GREEN.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from atdd.mediate_worker_decisions.coach_runtime.src.domain.managed_daemon import (
    ManagedDaemon,
)

_FEED_DAEMON_MODULE = (
    "atdd.mediate_worker_decisions.feed_daemon.src.presentation.feed_daemon_cli"
)


def workspace_slug(workspace_id: str) -> str:
    raise NotImplementedError("GREEN")


def build_feed_daemon_argv(
    *,
    python: str,
    workspace_id: str,
    lock_path: str,
    escalations_path: str,
    verdicts_path: str,
) -> List[str]:
    raise NotImplementedError("GREEN")


class ManagerRegistry:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def _dir(self, workspace_id: str) -> Path:
        return self._root / workspace_slug(workspace_id)

    def save(self, daemon: ManagedDaemon) -> None:
        raise NotImplementedError("GREEN")

    def load(self, workspace_id: str) -> Optional[ManagedDaemon]:
        raise NotImplementedError("GREEN")

    def load_all(self) -> List[ManagedDaemon]:
        raise NotImplementedError("GREEN")

    def remove(self, workspace_id: str) -> None:
        raise NotImplementedError("GREEN")


class SubprocessDaemonSpawner:
    def spawn(self, argv: List[str]) -> int:
        raise NotImplementedError("GREEN")


class OsLivenessProbe:
    def is_alive(self, pid: int) -> bool:
        raise NotImplementedError("GREEN")


class OsSignaller:
    def signal(self, pid: int, sig: int) -> None:
        raise NotImplementedError("GREEN")
