# URN: test:mediate-worker-decisions:feed-daemon:D002-INTEGRATION-001-run-forever-refuses-when-locked
# Acceptance: acc:mediate-worker-decisions:D002-INTEGRATION-001-run-forever-refuses-when-locked
# WMBT: wmbt:mediate-worker-decisions:D002
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""D002-INTEGRATION-001 — a second daemon refuses to run when the lock is held.

With a real PidfileLock already held at a path, a second daemon configured with
the same lock path raises SingleInstanceError from run_forever and never polls
the Feed.
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.feed_daemon.src.application.feed_daemon import (
    SingleInstanceError,
)
from atdd.mediate_worker_decisions.feed_daemon.src.integration.pidfile_lock import (
    PidfileLock,
)
from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import (
    SAFE_QUESTION,
    CountingFeedSource,
    make_daemon,
)


def test_second_daemon_refuses_when_lock_held(tmp_path):
    path = tmp_path / "daemon.lock"
    holder = PidfileLock(path)
    assert holder.acquire() is True

    source = CountingFeedSource([SAFE_QUESTION])
    daemon, _src, _transport, _coach = make_daemon(
        items=[SAFE_QUESTION], lock=PidfileLock(path), source=source
    )

    with pytest.raises(SingleInstanceError):
        daemon.run_forever()

    assert source.calls == 0  # never polled the Feed
    holder.release()
