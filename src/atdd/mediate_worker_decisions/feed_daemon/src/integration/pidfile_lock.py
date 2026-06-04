"""PidfileLock — feature-local single-instance guard (DG-4, WMBT D002).

acquire() writes our pid to the lock path iff no live holder owns it; a stale
pidfile (the named pid is not alive) is reclaimed so a crashed daemon does not
wedge the lock. acquire() returns False when a live holder already owns the path.

Skeleton: bodies land in GREEN.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

_log = logging.getLogger("atdd.feed_daemon")


class PidfileLock:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._held = False

    def acquire(self) -> bool:
        """Take the lock unless a LIVE holder already owns the pidfile.

        A pidfile naming a dead pid is stale and is reclaimed, so a crashed
        daemon never wedges the lock permanently.
        """
        if self._held:
            return True
        if self._path.exists() and self._holder_alive():
            return False
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(str(os.getpid()), encoding="utf-8")
        self._held = True
        return True

    def release(self) -> None:
        if not self._held:
            return
        try:
            self._path.unlink()
        except FileNotFoundError:
            _log.debug("pidfile already gone on release", extra={"path": str(self._path)})
        self._held = False

    def _holder_alive(self) -> bool:
        try:
            text = self._path.read_text(encoding="utf-8").strip()
        except OSError:
            _log.debug("pidfile unreadable; treating as stale", extra={"path": str(self._path)})
            return False
        try:
            pid = int(text)
        except ValueError:
            _log.debug("pidfile content not an int; treating as stale", extra={"path": str(self._path)})
            return False
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            _log.debug("pidfile holder not alive; stale", extra={"pid": pid})
            return False  # stale pidfile — holder is gone
        except PermissionError:
            _log.debug("pidfile holder owned by another user; alive", extra={"pid": pid})
            return True  # process exists, owned by another user
        except OSError:
            _log.debug("os.kill probe failed; treating holder as gone", extra={"pid": pid})
            return False
        return True
