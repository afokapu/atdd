# URN: test:mediate-worker-decisions:mediate-decision:M001-INTEGRATION-001-timeout-escalates
# Acceptance: acc:mediate-worker-decisions:M001-INTEGRATION-001-timeout-escalates
# WMBT: wmbt:mediate-worker-decisions:M001
# Phase: RED
# Layer: application
# Assertion: behavioral
"""M001-INTEGRATION-001 — coach silence escalates on timeout; no verdict."""
from __future__ import annotations

from atdd.mediate_worker_decisions.mediate_decision.composition import build_mediate_use_case
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    CAUSE_TIMEOUT, Escalation,
)
from atdd.mediate_worker_decisions.mediate_decision.tests._helpers import (
    FakeClock, FakeCoach, FakeSink, fixed_id, fixed_ts, make_request,
)


def test_m001_integration_001_timeout_escalates():
    coach = FakeCoach(reply="")            # never returns a DECISION
    verdicts, escalations = FakeSink(), FakeSink()
    uc = build_mediate_use_case(
        coach=coach, clock=FakeClock(), verdict_sink=verdicts,
        escalation_sink=escalations, id_factory=fixed_id, ts_factory=fixed_ts,
        timeout_seconds=10.0, poll_interval=2.0,
    )
    outcome = uc.handle(make_request())

    assert isinstance(outcome, Escalation)
    assert outcome.cause == CAUSE_TIMEOUT
    assert verdicts.records == []
