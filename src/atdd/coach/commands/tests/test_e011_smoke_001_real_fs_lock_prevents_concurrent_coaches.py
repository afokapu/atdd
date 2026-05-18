"""acc:govern-lifecycle:E011-SMOKE-001 — real filesystem lock prevents concurrent coaches."""
from __future__ import annotations

import pytest

from atdd.coach.utils.coach_lock import CoachAlreadyRunning, CoachLock


@pytest.mark.smoke
def test_real_fs_lock_prevents_concurrent_coaches(tmp_path):
    lock1 = CoachLock(tmp_path, issue_number=42)
    lock1.acquire()
    try:
        lock2 = CoachLock(tmp_path, issue_number=42)
        with pytest.raises(CoachAlreadyRunning):
            lock2.acquire()
    finally:
        lock1.release()

    # After release, a third acquisition must succeed.
    lock3 = CoachLock(tmp_path, issue_number=42)
    lock3.acquire()
    lock3.release()
