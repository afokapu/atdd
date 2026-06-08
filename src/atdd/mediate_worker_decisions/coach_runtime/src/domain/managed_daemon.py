"""Value object for a coach-managed feed_daemon (E010 / R003 / M005).

``ManagedDaemon`` is the durable record `atdd coach start` persists per watched
workspace: the daemon's OWN cmux workspace ref (the headless surface hosting it —
#1007: the daemon runs INSIDE a cmux surface so it is a socket-recognized process,
never an orphaned detached subprocess) plus the workspace-scoped ledger/lock paths
it was launched with. ``status`` is derived at list time (running|stale) from
whether the daemon workspace still exists; it is not part of the persisted identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

STATUS_RUNNING = "running"
STATUS_STALE = "stale"


@dataclass(frozen=True)
class ManagedDaemon:
    workspace_id: str  # the TARGET workspace the daemon watches
    daemon_workspace: str  # the daemon's OWN cmux workspace ref (its headless surface)
    lock_path: str
    escalations_path: str
    verdicts_path: str
    status: Optional[str] = None

    def to_record(self) -> dict:
        return {
            "workspace_id": self.workspace_id,
            "daemon_workspace": self.daemon_workspace,
            "lock_path": self.lock_path,
            "escalations_path": self.escalations_path,
            "verdicts_path": self.verdicts_path,
        }

    def with_status(self, status: str) -> "ManagedDaemon":
        return ManagedDaemon(
            workspace_id=self.workspace_id,
            daemon_workspace=self.daemon_workspace,
            lock_path=self.lock_path,
            escalations_path=self.escalations_path,
            verdicts_path=self.verdicts_path,
            status=status,
        )
