# URN: test:mediate-worker-decisions:mediate-decision:C002-INTEGRATION-001-gate-before-coach
# Acceptance: acc:mediate-worker-decisions:C002-INTEGRATION-001-gate-before-coach
# WMBT: wmbt:mediate-worker-decisions:C002
# Phase: RED
# Layer: application
# Assertion: behavioral
"""C002-INTEGRATION-001 — dangerous request escalates; coach is never called."""
from __future__ import annotations

from atdd.mediate_worker_decisions.mediate_decision.composition import build_mediate_use_case
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    CAUSE_DANGEROUS, Escalation,
)
from atdd.mediate_worker_decisions.mediate_decision.tests._helpers import (
    FakeClock, FakeCoach, FakeSink, fixed_id, fixed_ts, make_request,
)


def test_c002_integration_001_gate_before_coach():
    coach = FakeCoach(reply="DECISION: 1")
    verdicts, escalations = FakeSink(), FakeSink()
    uc = build_mediate_use_case(
        coach=coach, clock=FakeClock(), verdict_sink=verdicts,
        escalation_sink=escalations, id_factory=fixed_id, ts_factory=fixed_ts,
    )
    outcome = uc.handle(make_request(options=(("1", "git push to origin"), ("2", "Abort"))))

    assert isinstance(outcome, Escalation)
    assert outcome.cause == CAUSE_DANGEROUS
    assert coach.presented == []          # gate ran BEFORE the coach
    assert verdicts.records == []         # never auto-applied
    assert len(escalations.records) == 1
