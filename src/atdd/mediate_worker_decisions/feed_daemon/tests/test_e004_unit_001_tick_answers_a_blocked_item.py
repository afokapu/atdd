# URN: test:mediate-worker-decisions:feed-daemon:E004-UNIT-001-tick-answers-a-blocked-item
# Acceptance: acc:mediate-worker-decisions:E004-UNIT-001-tick-answers-a-blocked-item
# WMBT: wmbt:mediate-worker-decisions:E004
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E004-UNIT-001 — one tick answers a safe blocked item and records the verdict.

A single daemon tick over a safe question item consults the coach once, delivers
one feed reply, appends the verdict to the durable ledger, and marks the
request_id answered.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import (
    SAFE_QUESTION,
    RecordingVerdictLedger,
    make_daemon,
)


def test_tick_answers_a_blocked_item():
    ledger = RecordingVerdictLedger()
    daemon, source, transport, coach = make_daemon(
        items=[SAFE_QUESTION], verdict_ledger=ledger
    )

    outcomes = daemon.tick()

    assert len(coach.calls) == 1            # coach consulted once
    assert len(transport.calls) == 1        # reply delivered once
    assert len(ledger.records) == 1         # verdict durably recorded
    assert len(outcomes) == 1
    assert outcomes[0].verdict is not None
    assert outcomes[0].escalation is None
