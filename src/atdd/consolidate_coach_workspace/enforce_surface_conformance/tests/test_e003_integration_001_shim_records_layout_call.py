# URN: test:consolidate-coach-workspace:enforce-surface-conformance:E003-INTEGRATION-001-shim-records-layout-call
# Acceptance: acc:consolidate-coach-workspace:E003-INTEGRATION-001-shim-records-layout-call
# WMBT: wmbt:consolidate-coach-workspace:E003
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E003-INTEGRATION-001 — driving the flat-wagon shim
``apply_canonical_name_and_layout`` end-to-end with a recording multiplexer
backend records at least one real layout primitive call. The seam must delegate to
the feature; a rename plus a 'layout target' print alone is the #865 regression."""
from __future__ import annotations

from atdd.coach.utils.session_naming_apply import apply_canonical_name_and_layout
from atdd.consolidate_coach_workspace.enforce_surface_conformance.tests._helpers import (
    RecordingBackend,
)


def test_shim_invokes_a_real_layout_primitive():
    backend = RecordingBackend()
    apply_canonical_name_and_layout(
        backend, "surface:1", "ATDD865-worker-coach-layout", surface_count=1
    )
    # The shim must produce at least one real layout mutation, not just rename.
    assert backend.layout_calls(), (
        "apply_canonical_name_and_layout recorded no layout primitive — only "
        f"{backend.call_names()}. Print-theater regression (#865)."
    )


def test_shim_still_renames():
    backend = RecordingBackend()
    apply_canonical_name_and_layout(
        backend, "surface:1", "ATDD865-worker-coach-layout", surface_count=1
    )
    assert "rename" in backend.call_names()
