"""acc:govern-lifecycle:E011-UNIT-003 — dead PID in lockfile is cleaned; new lock created."""
from __future__ import annotations

import json
import os

import pytest

from atdd.coach.utils.coach_lock import CoachLock


def test_dead_pid_cleans_stale_lock(tmp_path):
    lock_dir = tmp_path / "coach" / "42"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / "coach.lock"
    # PID 0 is never a valid user process on any POSIX system.
    # os.kill(0, 0) sends to the process group, not a specific dead process,
    # so we use a very high PID that is vanishingly unlikely to exist and
    # monkey-patch _pid_alive to simulate the dead-process path cleanly.
    lock_path.write_text(
        json.dumps({"pid": 999999999, "issue": 42, "started_at": "2026-05-01T00:00:00Z"}),
        encoding="utf-8",
    )

    import atdd.coach.utils.coach_lock as _mod

    original = _mod._pid_alive
    try:
        _mod._pid_alive = lambda pid: False  # simulate dead process
        lock = CoachLock(tmp_path, issue_number=42)
        lock.acquire()
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["pid"] == os.getpid(), "new lock must contain current PID"
    finally:
        _mod._pid_alive = original
        lock.release()
