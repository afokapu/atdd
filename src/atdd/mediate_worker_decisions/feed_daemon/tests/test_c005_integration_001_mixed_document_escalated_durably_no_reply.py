# URN: test:mediate-worker-decisions:feed-daemon:C005-INTEGRATION-001-mixed-document-escalated-durably-no-reply
# Acceptance: acc:mediate-worker-decisions:C005-INTEGRATION-001-mixed-document-escalated-durably-no-reply
# WMBT: wmbt:mediate-worker-decisions:C005
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""C005-INTEGRATION-001 — the mixed-document escalation is durable, no reply.

Through the real JsonlEscalationSink: a document mixing a safe choice block with
a dangerous confirm block appends exactly one escalation record (matching the
escalation contract) to escalations.jsonl, and the transport reply verb is never
called for that request_id. Safe-block suggestions surface via the operator log,
never a partial reply.
"""
from __future__ import annotations

import json

from atdd.mediate_worker_decisions.feed_daemon.src.integration.jsonl_ledgers import (
    JsonlEscalationSink,
)
from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import make_daemon
from atdd.mediate_worker_decisions.feed_daemon.tests.test_c005_unit_001_mixed_document_escalates_whole import (
    MIXED_DOCUMENT,
)


def test_mixed_document_escalation_is_durable_and_unreplied(tmp_path):
    escalations = tmp_path / "escalations.jsonl"
    daemon, source, transport, coach = make_daemon(
        items=[MIXED_DOCUMENT],
        escalation_sink=JsonlEscalationSink(escalations),
    )

    daemon.tick()

    lines = escalations.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["request_id"] == "req-mix"
    assert record["cause"] == "dangerous_action"
    assert "escalation_id" in record and "raised_at" in record
    assert transport.calls == []  # never auto-replied
