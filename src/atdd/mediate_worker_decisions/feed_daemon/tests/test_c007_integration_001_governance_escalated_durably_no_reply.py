# URN: test:mediate-worker-decisions:feed-daemon:C007-INTEGRATION-001-governance-escalated-durably-no-reply
# Acceptance: acc:mediate-worker-decisions:C007-INTEGRATION-001-governance-escalated-durably-no-reply
# WMBT: wmbt:mediate-worker-decisions:C007
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""C007-INTEGRATION-001 — a governance sign-off is durably escalated, no reply.

Through the real JsonlEscalationSink and a real daemon tick over a REAL runner:
a phase-transition sign-off appends exactly one escalation record with
cause=operator_reserved to escalations.jsonl, the transport reply verb is never
called, and no verdict is recorded (the operator-reserved gate is never
auto-answered).

RED state: the runner has no operator_reserved classification, so the daemon
auto-answers the governance question and records a verdict instead.
"""
from __future__ import annotations

import json

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.feed_daemon.src.integration.jsonl_ledgers import (
    JsonlEscalationSink,
)
from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import (
    RecordingVerdictLedger,
    make_daemon,
)

GOVERNANCE_SIGN_OFF = FeedItem(
    id="f-gov",
    request_id="req-gov",
    kind="question",
    question_prompt="Approve → RED?",
    question_options=(
        {"id": "approve", "label": "Approve → RED", "description": ""},
        {"id": "hold", "label": "Hold in PLANNED", "description": ""},
    ),
)


def test_governance_escalation_written_and_no_reply(tmp_path):
    escalations = tmp_path / "escalations.jsonl"
    ledger = RecordingVerdictLedger()
    daemon, source, transport, coach = make_daemon(
        items=[GOVERNANCE_SIGN_OFF],
        escalation_sink=JsonlEscalationSink(escalations),
        verdict_ledger=ledger,
    )

    daemon.tick()

    lines = escalations.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["cause"] == "operator_reserved"
    assert record["request_id"] == "req-gov"
    assert "escalation_id" in record and "raised_at" in record

    assert transport.calls == []        # never auto-replied
    assert ledger.records == []         # no verdict recorded for the sign-off
