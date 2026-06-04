# URN: test:mediate-worker-decisions:feed-daemon:D002-UNIT-001-second-acquire-refused-stale-reclaimed
# Acceptance: acc:mediate-worker-decisions:D002-UNIT-001-second-acquire-refused-stale-reclaimed
# WMBT: wmbt:mediate-worker-decisions:D002
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""D002-UNIT-001 — a held lock refuses a second acquire; a stale pidfile reclaims.

A second PidfileLock on a path held by a live process returns False. A pidfile
naming a dead pid is stale and is reclaimed (acquire succeeds).
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.feed_daemon.src.integration.pidfile_lock import (
    PidfileLock,
)

_DEAD_PID = 2_147_483_646  # not a live process


def test_second_acquire_refused_while_held(tmp_path):
    path = tmp_path / "daemon.lock"
    first = PidfileLock(path)
    second = PidfileLock(path)

    assert first.acquire() is True
    assert second.acquire() is False  # live holder owns it

    first.release()


def test_stale_pidfile_is_reclaimed(tmp_path):
    path = tmp_path / "daemon.lock"
    path.write_text(str(_DEAD_PID))  # crashed daemon left a stale pidfile

    reclaimed = PidfileLock(path)

    assert reclaimed.acquire() is True  # dead pid -> reclaim
