# URN: test:mediate-worker-decisions:feed-daemon:M003-UNIT-001-decide-failure-logged-and-escalated-not-swallowed
# Acceptance: acc:mediate-worker-decisions:M003-UNIT-001-decide-failure-logged-and-escalated-not-swallowed
# WMBT: wmbt:mediate-worker-decisions:M003
# Phase: RED
# Layer: application
# Assertion: behavioral
"""M003-UNIT-001 — a decide failure is loud-logged and escalated, never swallowed.

When the runner raises while deciding a blocked item (the silent #1007 failure: the
LlmCoach ``claude -p`` call dies in the detached, no-TTY daemon context), one daemon
tick must surface the failure LOUDLY on the daemon logger AND record a human-required
``decide_failed`` escalation to the durable sink — then mark the request answered and
return so the loop keeps polling. It must never swallow the error into nothing (the
zero-verdicts/zero-escalations bug) and must never let the exception crash the loop.
"""
from __future__ import annotations

import logging

from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import (
    SAFE_QUESTION,
    RecordingEscalationSink,
    RecordingVerdictLedger,
    make_daemon,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    CAUSE_DECIDE_FAILED,
)


class _RaisingCoach:
    """A coach whose decide step fails — mirrors a dead ``claude -p`` in the daemon."""

    def __init__(self):
        self.calls = []

    def mediate(self, request):
        self.calls.append(request)
        raise RuntimeError("claude -p exited 1 in the detached daemon context")


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def test_decide_failure_logged_and_escalated_not_swallowed():
    escalations = RecordingEscalationSink()
    verdicts = RecordingVerdictLedger()
    daemon, source, transport, coach = make_daemon(
        items=[SAFE_QUESTION],
        coach=_RaisingCoach(),
        escalation_sink=escalations,
        verdict_ledger=verdicts,
    )

    handler = _ListHandler()
    logger = logging.getLogger("atdd.feed_daemon")
    logger.addHandler(handler)
    try:
        # The loop must NOT crash on a decide failure.
        outcomes = daemon.tick()
    finally:
        logger.removeHandler(handler)

    # Loud-logged: a WARNING+ record naming the failing request_id reached the sink.
    assert any(
        record.levelno >= logging.WARNING and SAFE_QUESTION.request_id in record.getMessage()
        for record in handler.records
    ), "the decide failure was not loud-logged with its request_id"

    # Escalated, not swallowed: a human-required decide_failed escalation was recorded,
    # and NO verdict was written (the daemon never silently claimed a decision).
    assert len(escalations.records) == 1
    assert escalations.records[0].request_id == SAFE_QUESTION.request_id
    assert escalations.records[0].cause == CAUSE_DECIDE_FAILED
    assert len(verdicts.records) == 0

    # The item is marked answered (the outcome carries the escalation) so the next
    # tick does not re-escalate it forever.
    assert len(outcomes) == 1
    assert outcomes[0].escalation is not None
    assert outcomes[0].verdict is None
    assert daemon._answered.seen(SAFE_QUESTION.request_id)
