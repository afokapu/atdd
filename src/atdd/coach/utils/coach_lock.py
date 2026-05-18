"""Per-issue PID lockfile for atdd coach (issue #724).

CoachLock acquires .atdd/runtime/coach/<N>/coach.lock on entry and
releases it on exit.  A stale lock (dead PID) is auto-cleaned.
CoachAlreadyRunning is raised when a live process holds the lock.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class CoachAlreadyRunning(Exception):
    """Raised when a live coach process already holds the issue lock."""


def _pid_alive(pid: int) -> bool:
    """Return True if *pid* is a running process, False otherwise."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError) as exc:
        logger.debug("pid %d is not alive: %s", pid, exc)
        return False


class CoachLock:
    """Context-manager PID lockfile guard for one coach issue.

    Usage::

        with CoachLock(runtime_dir, issue_number=N):
            # only one process reaches here at a time
            ...

    The lockfile lives at ``<runtime_dir>/coach/<N>/coach.lock`` and contains
    JSON with ``pid``, ``issue``, and ``started_at``.
    """

    def __init__(self, runtime_dir: Path, issue_number: int) -> None:
        self._issue_number = issue_number
        self._dir = Path(runtime_dir) / "coach" / str(issue_number)
        self._lock_path = self._dir / "coach.lock"
        self._held = False

    def acquire(self) -> None:
        """Acquire the lock or raise CoachAlreadyRunning.

        Stale locks (PID no longer alive) are cleaned automatically.
        """
        self._dir.mkdir(parents=True, exist_ok=True)

        if self._lock_path.exists():
            try:
                data = json.loads(self._lock_path.read_text(encoding="utf-8"))
                pid = int(data.get("pid", 0))
            except (OSError, ValueError, json.JSONDecodeError):
                pid = 0
                data = {}

            if pid and _pid_alive(pid):
                raise CoachAlreadyRunning(
                    f"coach already running for #{self._issue_number}, pid {pid}"
                )
            # Stale lock — clean and proceed.
            self._lock_path.unlink(missing_ok=True)

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._lock_path.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "issue": self._issue_number,
                    "started_at": now,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        self._held = True
        atexit.register(self._release_atexit)

    def release(self) -> None:
        """Release the lock (idempotent)."""
        if self._held:
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.debug("coach lock release failed for %s: %s", self._lock_path, exc)
            self._held = False

    def _release_atexit(self) -> None:
        self.release()

    def __enter__(self) -> "CoachLock":
        self.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        self.release()
