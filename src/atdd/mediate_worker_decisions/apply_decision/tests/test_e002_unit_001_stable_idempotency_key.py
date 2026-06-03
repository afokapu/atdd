# URN: test:mediate-worker-decisions:apply-decision:E002-UNIT-001-stable-idempotency-key
# Acceptance: acc:mediate-worker-decisions:E002-UNIT-001-stable-idempotency-key
# WMBT: wmbt:mediate-worker-decisions:E002
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""E002-UNIT-001 — The idempotency key is stable for the same request+verdict and differs across distinct ones

RED: the apply-decision four-tier slice is not implemented yet; this test fails until
the GREEN phase wires apply-decision's domain/application/integration tiers.
"""
from __future__ import annotations

import pytest


def test_e002_unit_001_stable_idempotency_key():
    # RED placeholder — importing the feature composition root raises until GREEN.
    from atdd.mediate_worker_decisions.apply_decision import composition  # noqa: F401

    pytest.fail("RED: acc:mediate-worker-decisions:E002-UNIT-001-stable-idempotency-key not yet implemented")
