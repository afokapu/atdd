"""Value object for a coach-managed feed_daemon (E010 / R003).

``ManagedDaemon`` is the durable record `atdd coach start` persists per
workspace: the spawned pid plus the workspace-scoped ledger/lock paths the
daemon was launched with. ``status`` is derived at list time (running|stale)
from a liveness probe; it is not part of the persisted identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

STATUS_RUNNING = "running"
STATUS_STALE = "stale"


@dataclass(frozen=True)
class ManagedDaemon:
    workspace_id: str
    pid: int
    lock_path: str
    escalations_path: str
    verdicts_path: str
    status: Optional[str] = None

    def to_record(self) -> dict:
        return {
            "workspace_id": self.workspace_id,
            "pid": self.pid,
            "lock_path": self.lock_path,
            "escalations_path": self.escalations_path,
            "verdicts_path": self.verdicts_path,
        }

    def with_status(self, status: str) -> "ManagedDaemon":
        return ManagedDaemon(
            workspace_id=self.workspace_id,
            pid=self.pid,
            lock_path=self.lock_path,
            escalations_path=self.escalations_path,
            verdicts_path=self.verdicts_path,
            status=status,
        )
