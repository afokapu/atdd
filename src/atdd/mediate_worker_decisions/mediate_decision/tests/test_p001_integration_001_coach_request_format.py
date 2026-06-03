# URN: test:mediate-worker-decisions:mediate-decision:P001-INTEGRATION-001-coach-request-format
# Acceptance: acc:mediate-worker-decisions:P001-INTEGRATION-001-coach-request-format
# WMBT: wmbt:mediate-worker-decisions:P001
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""P001-INTEGRATION-001 — The coach client renders the request (wagon, worker, question, options) and sends it to the coach surface in the DECISION:/REASON: contract

RED: the mediate-decision four-tier slice is not implemented yet; this test fails until
the GREEN phase wires mediate-decision's domain/application/integration tiers.
"""
from __future__ import annotations

import pytest


def test_p001_integration_001_coach_request_format():
    # RED placeholder — importing the feature composition root raises until GREEN.
    from atdd.mediate_worker_decisions.mediate_decision import composition  # noqa: F401

    pytest.fail("RED: acc:mediate-worker-decisions:P001-INTEGRATION-001-coach-request-format not yet implemented")
