# URN: test:mediate-worker-decisions:sense-decision:D001-UNIT-001-surface-maps-to-one-worker
# Acceptance: acc:mediate-worker-decisions:D001-UNIT-001-surface-maps-to-one-worker
# WMBT: wmbt:mediate-worker-decisions:D001
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""D001-UNIT-001 — a known surface resolves to exactly one worker; unknown -> None."""
from __future__ import annotations

from atdd.mediate_worker_decisions.sense_decision.src.integration.registry_worker_lookup import (
    RegistryWorkerLookup,
)


def test_d001_unit_001_surface_maps_to_one_worker():
    registry = RegistryWorkerLookup(
        {"surface:3": {"run_id": "run-1", "agent_handle_ref": "h-3"}}
    )

    worker = registry.resolve("surface:3")
    assert worker is not None
    assert worker.surface_id == "surface:3"
    assert worker.run_id == "run-1"
    assert worker.agent_handle_ref == "h-3"

    # Unknown surface fabricates no worker.
    assert registry.resolve("surface:99") is None
