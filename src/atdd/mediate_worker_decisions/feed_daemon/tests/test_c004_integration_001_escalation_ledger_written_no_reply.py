# URN: test:mediate-worker-decisions:feed-daemon:C004-INTEGRATION-001-escalation-ledger-written-no-reply
# Acceptance: acc:mediate-worker-decisions:C004-INTEGRATION-001-escalation-ledger-written-no-reply
# WMBT: wmbt:mediate-worker-decisions:C004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""C004-INTEGRATION-001 — the dangerous escalation is durably recorded, no reply.

Through the real JsonlEscalationSink: a dangerous item appends exactly one
escalation record (matching the escalation contract shape) to escalations.jsonl,
and the transport reply verb is never called.
"""
from __future__ import annotations

import json

from atdd.mediate_worker_decisions.feed_daemon.src.integration.jsonl_ledgers import (
    JsonlEscalationSink,
)
from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import (
    DANGER_PERMISSION,
    make_daemon,
)


def test_escalation_written_and_no_reply(tmp_path):
    escalations = tmp_path / "escalations.jsonl"
    daemon, source, transport, coach = make_daemon(
        items=[DANGER_PERMISSION],
        escalation_sink=JsonlEscalationSink(escalations),
    )

    daemon.tick()

    lines = escalations.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["cause"] == "dangerous_action"
    assert record["request_id"] == "req-danger"
    assert "escalation_id" in record and "raised_at" in record
    assert transport.calls == []  # never auto-replied
