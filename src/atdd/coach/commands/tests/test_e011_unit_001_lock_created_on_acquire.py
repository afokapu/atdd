"""acc:govern-lifecycle:E011-UNIT-001 — lockfile created with PID + timestamp on acquire."""
from __future__ import annotations

import json
import os

import pytest

from atdd.coach.utils.coach_lock import CoachLock


def test_lock_created_on_acquire(tmp_path):
    lock = CoachLock(tmp_path, issue_number=42)
    lock.acquire()
    try:
        lock_path = tmp_path / "coach" / "42" / "coach.lock"
        assert lock_path.exists(), "lockfile must be created"
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["pid"] == os.getpid()
        assert data["issue"] == 42
        assert "started_at" in data
        assert data["started_at"].endswith("Z") or "T" in data["started_at"]
    finally:
        lock.release()
