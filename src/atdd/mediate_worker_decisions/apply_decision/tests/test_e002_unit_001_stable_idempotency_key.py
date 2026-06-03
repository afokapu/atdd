# URN: test:mediate-worker-decisions:apply-decision:E002-UNIT-001-stable-idempotency-key
# Acceptance: acc:mediate-worker-decisions:E002-UNIT-001-stable-idempotency-key
# WMBT: wmbt:mediate-worker-decisions:E002
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""E002-UNIT-001 — idempotency key is stable per (request, verdict) and unique across."""
from __future__ import annotations

from atdd.mediate_worker_decisions.apply_decision.src.domain.idempotency_key import idempotency_key


def test_stable_and_unique():
    a = idempotency_key("req-1", "ver-1")
    assert a == idempotency_key("req-1", "ver-1")
    assert a != idempotency_key("req-1", "ver-2")
    assert a != idempotency_key("req-2", "ver-1")
