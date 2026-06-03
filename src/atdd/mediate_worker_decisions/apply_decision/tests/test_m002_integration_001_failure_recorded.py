# URN: test:mediate-worker-decisions:apply-decision:M002-INTEGRATION-001-failure-recorded
# Acceptance: acc:mediate-worker-decisions:M002-INTEGRATION-001-failure-recorded
# WMBT: wmbt:mediate-worker-decisions:M002
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""M002-INTEGRATION-001 — When delivery raises, a record with disposition application_failed and the error is written, and no success is reported

RED: the apply-decision four-tier slice is not implemented yet; this test fails until
the GREEN phase wires apply-decision's domain/application/integration tiers.
"""
from __future__ import annotations

import pytest


def test_m002_integration_001_failure_recorded():
    # RED placeholder — importing the feature composition root raises until GREEN.
    from atdd.mediate_worker_decisions.apply_decision import composition  # noqa: F401

    pytest.fail("RED: acc:mediate-worker-decisions:M002-INTEGRATION-001-failure-recorded not yet implemented")
