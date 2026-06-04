# URN: test:mediate-worker-decisions:feed-daemon:R002-UNIT-001-stop-signal-exits-loop-and-releases-lock
# Acceptance: acc:mediate-worker-decisions:R002-UNIT-001-stop-signal-exits-loop-and-releases-lock
# WMBT: wmbt:mediate-worker-decisions:R002
# Phase: RED
# Layer: application
# Assertion: behavioral
"""R002-UNIT-001 — a stop signal exits the loop and releases the lock.

With a stop signal that flips after the first tick, run_forever performs a
bounded number of ticks and returns, releasing the single-instance lock exactly
once (in a finally block).
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import (
    FakeSleeper,
    FlipStop,
    RecordingLock,
    make_daemon,
)


def test_stop_exits_loop_and_releases_lock():
    sleeper = FakeSleeper()
    lock = RecordingLock(acquired=True)
    stop = FlipStop([False, True])  # run one tick, then stop
    daemon, source, transport, coach = make_daemon(
        items=[], sleeper=sleeper, stop=stop, lock=lock, poll_interval_s=0.0
    )

    daemon.run_forever()

    assert lock.acquires == 1       # acquired once
    assert lock.releases == 1       # released exactly once on shutdown
    assert len(sleeper.calls) == 1  # exactly one tick cycle before stop
