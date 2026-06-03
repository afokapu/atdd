# URN: test:mediate-worker-decisions:sense-decision:L001-UNIT-001-extracts-latest-prompt
# Acceptance: acc:mediate-worker-decisions:L001-UNIT-001-extracts-latest-prompt
# WMBT: wmbt:mediate-worker-decisions:L001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""L001-UNIT-001 — The pure parser extracts the question and option list, choosing the latest prompt when several appear

RED: the sense-decision four-tier slice is not implemented yet; this test fails until
the GREEN phase wires sense-decision's domain/application/integration tiers.
"""
from __future__ import annotations

import pytest


def test_l001_unit_001_extracts_latest_prompt():
    # RED placeholder — importing the feature composition root raises until GREEN.
    from atdd.mediate_worker_decisions.sense_decision import composition  # noqa: F401

    pytest.fail("RED: acc:mediate-worker-decisions:L001-UNIT-001-extracts-latest-prompt not yet implemented")
