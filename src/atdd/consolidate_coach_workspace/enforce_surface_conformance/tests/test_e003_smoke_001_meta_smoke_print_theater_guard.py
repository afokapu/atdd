# URN: test:consolidate-coach-workspace:enforce-surface-conformance:E003-SMOKE-001-meta-smoke-print-theater-guard
# Acceptance: acc:consolidate-coach-workspace:E003-SMOKE-001-meta-smoke-print-theater-guard
# WMBT: wmbt:consolidate-coach-workspace:E003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E003-SMOKE-001 — print-theater meta-smoke (issue #865 L002).

Drives the full feature conformance pass through a recording multiplexer backend
and asserts a real backend layout primitive was observed for each placed worker.
A layout-target print with zero layout primitive calls FAILS this smoke — that is
the exact regression this guard exists to catch. By design this meta-smoke uses a
recording fake (it asserts that the production path *invokes* the backend), so it
runs without live cmux."""
from __future__ import annotations

from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.presentation.apply_conformance import (
    apply_surface_conformance,
)
from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.layout_plan import (
    WorkerSurface,
)
from atdd.consolidate_coach_workspace.enforce_surface_conformance.tests._helpers import (
    RecordingBackend,
)


def test_conformance_pass_invokes_backend_layout_primitive():
    backend = RecordingBackend()
    workers = [
        WorkerSurface("surface:1", "workspace:1", "claude-1"),
        WorkerSurface("surface:2", "workspace:2", "claude-2"),
    ]
    apply_surface_conformance(
        backend,
        coach_pane="pane:coach",
        coach_workspace_id="workspace:coach",
        workers=workers,
    )
    layout_calls = backend.layout_calls()
    assert layout_calls, (
        "conformance pass recorded no backend layout primitive — print-theater "
        f"regression (#865). Recorded: {backend.call_names()}"
    )
    # One real layout mutation per worker placed (no print substituting for work).
    assert len(layout_calls) >= len(workers)
