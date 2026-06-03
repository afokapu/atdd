# URN: test:mediate-worker-decisions:apply-decision:E002-SMOKE-001-close-the-loop
# Acceptance: acc:mediate-worker-decisions:E002-SMOKE-001-close-the-loop
# WMBT: wmbt:mediate-worker-decisions:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E002-SMOKE-001 — A live verdict delivered to a real blocked worker unblocks it and the prompt no longer fires

RED: the apply-decision four-tier slice is not implemented yet; this test fails until
the GREEN phase wires apply-decision's domain/application/integration tiers.
"""
from __future__ import annotations

import pytest


def test_e002_smoke_001_close_the_loop():
    # RED placeholder — importing the feature composition root raises until GREEN.
    from atdd.mediate_worker_decisions.apply_decision import composition  # noqa: F401

    pytest.fail("RED: acc:mediate-worker-decisions:E002-SMOKE-001-close-the-loop not yet implemented")
