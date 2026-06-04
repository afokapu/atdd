# URN: test:mediate-worker-decisions:feed-daemon:C004-UNIT-001-dangerous-escalates-not-auto
# Acceptance: acc:mediate-worker-decisions:C004-UNIT-001-dangerous-escalates-not-auto
# WMBT: wmbt:mediate-worker-decisions:C004
# Phase: RED
# Layer: application
# Assertion: behavioral
"""C004-UNIT-001 — a dangerous item is escalated, never auto-answered.

The headline safety property: a dangerous permission item in a tick is recorded
to the escalation sink AND loudly logged (WARNING), the transport reply verb is
never called, and the coach is never consulted.
"""
from __future__ import annotations

import logging

from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import (
    DANGER_PERMISSION,
    RecordingEscalationSink,
    make_daemon,
)


def test_dangerous_item_escalates_and_is_not_auto_answered(caplog):
    sink = RecordingEscalationSink()
    daemon, source, transport, coach = make_daemon(
        items=[DANGER_PERMISSION], escalation_sink=sink
    )

    with caplog.at_level(logging.WARNING, logger="atdd.feed_daemon"):
        outcomes = daemon.tick()

    assert len(sink.records) == 1                      # escalation recorded
    assert sink.records[0].cause == "dangerous_action"
    assert transport.calls == []                       # NO auto reply
    assert coach.calls == []                           # coach never consulted
    assert outcomes[0].escalation is not None
    assert any(r.levelno >= logging.WARNING for r in caplog.records)  # loud log
