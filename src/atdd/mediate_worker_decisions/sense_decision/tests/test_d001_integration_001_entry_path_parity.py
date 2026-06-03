# URN: test:mediate-worker-decisions:sense-decision:D001-INTEGRATION-001-entry-path-parity
# Acceptance: acc:mediate-worker-decisions:D001-INTEGRATION-001-entry-path-parity
# WMBT: wmbt:mediate-worker-decisions:D001
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""D001-INTEGRATION-001 — notify-hook and emit-CLI serialize a byte-identical request (modulo provenance.source) via one shared RequestSink

RED: the sense-decision four-tier slice is not implemented yet; this test fails until
the GREEN phase wires sense-decision's domain/application/integration tiers.
"""
from __future__ import annotations

import pytest


def test_d001_integration_001_entry_path_parity():
    # RED placeholder — importing the feature composition root raises until GREEN.
    from atdd.mediate_worker_decisions.sense_decision import composition  # noqa: F401

    pytest.fail("RED: acc:mediate-worker-decisions:D001-INTEGRATION-001-entry-path-parity not yet implemented")
