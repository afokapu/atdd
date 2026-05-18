"""acc:govern-lifecycle:E011-UNIT-002 — live PID in lockfile raises CoachAlreadyRunning."""
from __future__ import annotations

import json
import os

import pytest

from atdd.coach.utils.coach_lock import CoachAlreadyRunning, CoachLock


def test_live_pid_raises_already_running(tmp_path):
    lock_dir = tmp_path / "coach" / "42"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / "coach.lock"
    # Use our own PID — guaranteed alive.
    lock_path.write_text(
        json.dumps({"pid": os.getpid(), "issue": 42, "started_at": "2026-05-19T00:00:00Z"}),
        encoding="utf-8",
    )

    lock = CoachLock(tmp_path, issue_number=42)
    with pytest.raises(CoachAlreadyRunning) as exc_info:
        lock.acquire()

    msg = str(exc_info.value)
    assert str(os.getpid()) in msg, "message must name the PID"
    assert "42" in msg, "message must name the issue"
    # The existing lockfile must not be removed
    assert lock_path.exists(), "live lock must remain on disk"
