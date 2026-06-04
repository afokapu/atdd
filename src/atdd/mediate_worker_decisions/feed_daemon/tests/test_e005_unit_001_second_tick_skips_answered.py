# URN: test:mediate-worker-decisions:feed-daemon:E005-UNIT-001-second-tick-skips-answered
# Acceptance: acc:mediate-worker-decisions:E005-UNIT-001-second-tick-skips-answered
# WMBT: wmbt:mediate-worker-decisions:E005
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E005-UNIT-001 — the same item across two ticks is answered exactly once.

The answered-set skips a request_id already handled, so the coach is never
re-paid and no second reply is delivered on the second tick.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import (
    SAFE_QUESTION,
    make_daemon,
)


def test_second_tick_does_not_re_answer():
    daemon, source, transport, coach = make_daemon(items=[SAFE_QUESTION])

    daemon.tick()
    daemon.tick()  # same item still pending — must be skipped

    assert len(coach.calls) == 1       # coach consulted exactly once
    assert len(transport.calls) == 1   # reply delivered exactly once
