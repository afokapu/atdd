# URN: test:mediate-worker-decisions:apply-decision:R001-UNIT-001-human-required-not-applied
# Acceptance: acc:mediate-worker-decisions:R001-UNIT-001-human-required-not-applied
# WMBT: wmbt:mediate-worker-decisions:R001
# Phase: RED
# Layer: application
# Assertion: behavioral
"""R001-UNIT-001 — a human_required verdict is never delivered; recorded as escalated."""
from __future__ import annotations

from atdd.mediate_worker_decisions.apply_decision.composition import build_apply_use_case
from atdd.mediate_worker_decisions.apply_decision.src.domain.record import ESCALATED
from atdd.mediate_worker_decisions.apply_decision.src.integration.agent_control_applier import (
    InMemoryAppliedGuard,
)
from atdd.mediate_worker_decisions.apply_decision.tests._helpers import (
    FakeApplier, FakeLedger, fixed_id, fixed_ts, make_request, make_verdict,
)


def test_human_required_not_applied():
    applier, ledger = FakeApplier(), FakeLedger()
    uc = build_apply_use_case(
        applier=applier, ledger=ledger, guard=InMemoryAppliedGuard(),
        id_factory=fixed_id, ts_factory=fixed_ts,
    )
    rec = uc.apply(make_request(), make_verdict(auto=False))

    assert applier.calls == []            # never delivered
    assert rec.disposition == ESCALATED
