# URN: test:mediate-worker-decisions:feed-daemon-durability:R005-UNIT-002-record-failure-escalates-and-logs
# Acceptance: acc:mediate-worker-decisions:R005-UNIT-002-record-failure-escalates-and-logs
# WMBT: wmbt:mediate-worker-decisions:R005
# Phase: RED
# Layer: application
# Assertion: behavioral
"""R005-UNIT-002 — a record() write failure escalates loudly, never silently dropped.

When the durable verdict write fails, the dropped verdict must not vanish: the
daemon loud-logs a WARNING and records an escalation so the lost write leaves a
durable trace — then keeps polling (the survival property of R005-UNIT-001).

RED: today the unguarded record() raise crashes the tick before any warning or
escalation is emitted. Fails until record() is wrapped to escalate-and-log.
"""
from __future__ import annotations

import logging

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import (
    RecordingEscalationSink,
    make_daemon,
)


def _safe_question(suffix):
    return FeedItem(
        id=f"f-{suffix}",
        request_id=f"req-{suffix}",
        kind="question",
        question_prompt="Pick an option",
        question_options=(
            {"id": "Alpha", "label": "Alpha", "description": ""},
            {"id": "Beta", "label": "Beta", "description": ""},
        ),
        tool_name=None,
        tool_input=None,
    )


class _RaisingVerdictLedger:
    def record(self, verdict):
        raise OSError("No space left on device")


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def test_record_failure_escalates_and_logs():
    item = _safe_question("solo")
    escalations = RecordingEscalationSink()
    daemon, source, transport, coach = make_daemon(
        items=[item],
        verdict_ledger=_RaisingVerdictLedger(),
        escalation_sink=escalations,
    )

    handler = _ListHandler()
    logger = logging.getLogger("atdd.feed_daemon")
    logger.addHandler(handler)
    try:
        daemon.tick()
    finally:
        logger.removeHandler(handler)

    # Loud-logged: a WARNING+ record naming the failing request_id was emitted.
    assert any(
        rec.levelno >= logging.WARNING and item.request_id in rec.getMessage()
        for rec in handler.records
    ), "the record() failure was not loud-logged with its request_id (R005)"

    # Escalated, not silently swallowed: the dropped verdict left a durable trace.
    assert len(escalations.records) >= 1, (
        "a record() write failure must record an escalation so the dropped "
        "verdict is recoverable — got none (R005)"
    )
