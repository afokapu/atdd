# URN: test:mediate-worker-decisions:mediate-decision:P001-INTEGRATION-001-coach-request-format
# Acceptance: acc:mediate-worker-decisions:P001-INTEGRATION-001-coach-request-format
# WMBT: wmbt:mediate-worker-decisions:P001
# Phase: RED
# Layer: application
# Assertion: behavioral
"""P001-INTEGRATION-001 — the coach request carries question, options, and the reply contract."""
from __future__ import annotations

from atdd.mediate_worker_decisions.mediate_decision.composition import build_mediate_use_case
from atdd.mediate_worker_decisions.mediate_decision.tests._helpers import (
    FakeClock, FakeCoach, FakeSink, fixed_id, fixed_ts, make_request,
)


def test_p001_integration_001_coach_request_format():
    coach = FakeCoach(reply="DECISION: 1\nREASON: ok")
    uc = build_mediate_use_case(
        coach=coach, clock=FakeClock(), verdict_sink=FakeSink(),
        escalation_sink=FakeSink(), id_factory=fixed_id, ts_factory=fixed_ts,
    )
    uc.handle(make_request(question="Proceed?", options=(("1", "Yes"), ("2", "No"))))

    sent = coach.presented[0]
    assert "Proceed?" in sent
    assert "1)" in sent and "2)" in sent
    assert "DECISION:" in sent and "REASON:" in sent
