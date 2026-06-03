# URN: test:mediate-worker-decisions:apply-decision:K001-INTEGRATION-001-record-written
# Acceptance: acc:mediate-worker-decisions:K001-INTEGRATION-001-record-written
# WMBT: wmbt:mediate-worker-decisions:K001
# Phase: RED
# Layer: application
# Assertion: behavioral
"""K001-INTEGRATION-001 — applying writes a record embedding request, verdict, disposition."""
from __future__ import annotations

from atdd.mediate_worker_decisions.apply_decision.composition import build_apply_use_case
from atdd.mediate_worker_decisions.apply_decision.src.domain.record import APPLIED
from atdd.mediate_worker_decisions.apply_decision.src.integration.agent_control_applier import (
    InMemoryAppliedGuard,
)
from atdd.mediate_worker_decisions.apply_decision.tests._helpers import (
    FakeApplier, FakeLedger, fixed_id, fixed_ts, make_request, make_verdict,
)


def test_record_written():
    ledger = FakeLedger()
    uc = build_apply_use_case(
        applier=FakeApplier(), ledger=ledger, guard=InMemoryAppliedGuard(),
        id_factory=fixed_id, ts_factory=fixed_ts,
    )
    rec = uc.apply(make_request(), make_verdict())

    assert len(ledger.records) == 1
    assert rec.disposition == APPLIED
    assert rec.request is not None and rec.request["request_id"] == "req-1"
    assert rec.verdict is not None and rec.verdict["disposition"] == "auto_apply"
