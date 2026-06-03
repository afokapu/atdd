# URN: test:mediate-worker-decisions:apply-decision:M002-INTEGRATION-001-failure-recorded
# Acceptance: acc:mediate-worker-decisions:M002-INTEGRATION-001-failure-recorded
# WMBT: wmbt:mediate-worker-decisions:M002
# Phase: RED
# Layer: application
# Assertion: behavioral
"""M002-INTEGRATION-001 — a delivery failure is recorded, not swallowed or reported applied."""
from __future__ import annotations

from atdd.mediate_worker_decisions.apply_decision.composition import build_apply_use_case
from atdd.mediate_worker_decisions.apply_decision.src.domain.record import APPLICATION_FAILED
from atdd.mediate_worker_decisions.apply_decision.src.integration.agent_control_applier import (
    InMemoryAppliedGuard,
)
from atdd.mediate_worker_decisions.apply_decision.tests._helpers import (
    FakeApplier, FakeLedger, fixed_id, fixed_ts, make_request, make_verdict,
)


def test_failure_recorded():
    ledger = FakeLedger()
    uc = build_apply_use_case(
        applier=FakeApplier(raises=True), ledger=ledger, guard=InMemoryAppliedGuard(),
        id_factory=fixed_id, ts_factory=fixed_ts,
    )
    rec = uc.apply(make_request(), make_verdict())   # must not raise

    assert rec.disposition == APPLICATION_FAILED
    assert rec.error and "deliver failed" in rec.error
    assert len(ledger.records) == 1
