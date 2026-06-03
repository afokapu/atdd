# URN: test:mediate-worker-decisions:sense-decision:D001-SMOKE-001-live-resolve
# Acceptance: acc:mediate-worker-decisions:D001-SMOKE-001-live-resolve
# WMBT: wmbt:mediate-worker-decisions:D001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""D001-SMOKE-001 — A live cmux notification resolves through the real registry to the worker that raised it

RED: the sense-decision four-tier slice is not implemented yet; this test fails until
the GREEN phase wires sense-decision's domain/application/integration tiers.
"""
from __future__ import annotations

import pytest


def test_d001_smoke_001_live_resolve():
    # RED placeholder — importing the feature composition root raises until GREEN.
    from atdd.mediate_worker_decisions.sense_decision import composition  # noqa: F401

    pytest.fail("RED: acc:mediate-worker-decisions:D001-SMOKE-001-live-resolve not yet implemented")
