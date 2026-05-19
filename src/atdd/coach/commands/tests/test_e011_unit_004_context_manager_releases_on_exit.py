# URN: test:govern-lifecycle:coach-single-instance-lock-and-zombie-reaping:E011-UNIT-004-context-manager-releases-on-exit
# Acceptance: acc:govern-lifecycle:E011-UNIT-004-context-manager-releases-on-exit
# WMBT: wmbt:govern-lifecycle:E011
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E011-UNIT-004 — context manager releases lockfile on exit."""
from __future__ import annotations

import pytest

from atdd.coach.utils.coach_lock import CoachLock


def test_context_manager_releases_on_exit(tmp_path):
    lock_path = tmp_path / "coach" / "42" / "coach.lock"

    with CoachLock(tmp_path, issue_number=42):
        assert lock_path.exists(), "lockfile must exist inside the with block"

    assert not lock_path.exists(), "lockfile must be removed after with block exits"
