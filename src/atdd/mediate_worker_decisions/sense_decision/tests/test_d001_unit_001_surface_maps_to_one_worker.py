# URN: test:mediate-worker-decisions:sense-decision:D001-UNIT-001-surface-maps-to-one-worker
# Acceptance: acc:mediate-worker-decisions:D001-UNIT-001-surface-maps-to-one-worker
# WMBT: wmbt:mediate-worker-decisions:D001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""D001-UNIT-001 — A known surface id resolves to exactly one worker; an unknown surface id resolves to None (no worker invented)

RED: the sense-decision four-tier slice is not implemented yet; this test fails until
the GREEN phase wires sense-decision's domain/application/integration tiers.
"""
from __future__ import annotations

import pytest


def test_d001_unit_001_surface_maps_to_one_worker():
    # RED placeholder — importing the feature composition root raises until GREEN.
    from atdd.mediate_worker_decisions.sense_decision import composition  # noqa: F401

    pytest.fail("RED: acc:mediate-worker-decisions:D001-UNIT-001-surface-maps-to-one-worker not yet implemented")
