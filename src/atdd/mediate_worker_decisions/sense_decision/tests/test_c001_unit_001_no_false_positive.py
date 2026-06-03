# URN: test:mediate-worker-decisions:sense-decision:C001-UNIT-001-no-false-positive
# Acceptance: acc:mediate-worker-decisions:C001-UNIT-001-no-false-positive
# WMBT: wmbt:mediate-worker-decisions:C001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C001-UNIT-001 — Non-decision text (empty, progress, or partially-rendered prompt) yields no request

RED: the sense-decision four-tier slice is not implemented yet; this test fails until
the GREEN phase wires sense-decision's domain/application/integration tiers.
"""
from __future__ import annotations

import pytest


def test_c001_unit_001_no_false_positive():
    # RED placeholder — importing the feature composition root raises until GREEN.
    from atdd.mediate_worker_decisions.sense_decision import composition  # noqa: F401

    pytest.fail("RED: acc:mediate-worker-decisions:C001-UNIT-001-no-false-positive not yet implemented")
