# URN: test:mediate-worker-decisions:apply-decision:E002-INTEGRATION-001-applied-once
# Acceptance: acc:mediate-worker-decisions:E002-INTEGRATION-001-applied-once
# WMBT: wmbt:mediate-worker-decisions:E002
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E002-INTEGRATION-001 — the same verdict is delivered exactly once."""
from __future__ import annotations

from atdd.mediate_worker_decisions.apply_decision.composition import build_apply_use_case
from atdd.mediate_worker_decisions.apply_decision.src.integration.agent_control_applier import (
    InMemoryAppliedGuard,
)
from atdd.mediate_worker_decisions.apply_decision.tests._helpers import (
    FakeApplier, FakeLedger, fixed_id, fixed_ts, make_request, make_verdict,
)


def test_applied_once():
    applier, ledger = FakeApplier(), FakeLedger()
    uc = build_apply_use_case(
        applier=applier, ledger=ledger, guard=InMemoryAppliedGuard(),
        id_factory=fixed_id, ts_factory=fixed_ts,
    )
    req, verdict = make_request(), make_verdict()
    uc.apply(req, verdict)
    uc.apply(req, verdict)            # replay

    assert len(applier.calls) == 1   # delivered once
    assert len(ledger.records) == 2  # applied, then deduped
