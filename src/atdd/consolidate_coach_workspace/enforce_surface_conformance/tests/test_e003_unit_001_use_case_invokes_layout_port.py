# URN: test:consolidate-coach-workspace:enforce-surface-conformance:E003-UNIT-001-use-case-invokes-layout-port
# Acceptance: acc:consolidate-coach-workspace:E003-UNIT-001-use-case-invokes-layout-port
# WMBT: wmbt:consolidate-coach-workspace:E003
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E003-UNIT-001 — the apply-layout use case invokes a REAL layout primitive
through the port (create_right_pane / place_surface_right), not a print-only
no-op. This is the core #865 anti-log-theater guarantee at the application tier."""
from __future__ import annotations

from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.application.apply_layout_use_case import (
    ApplyLayoutUseCase,
)
from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.layout_plan import (
    WorkerSurface,
)
from atdd.consolidate_coach_workspace.enforce_surface_conformance.tests._helpers import (
    FakeLogger,
    FakeScopeProbe,
    RecordingLayoutPort,
)

COACH_WS = "workspace:coach"
COACH_PANE = "pane:coach"


def _build():
    layout = RecordingLayoutPort()
    workers = [
        WorkerSurface("surface:1", "workspace:1", "claude-1"),
        WorkerSurface("surface:2", "workspace:2", "claude-2"),
    ]
    probe = FakeScopeProbe({w.workspace_id: [w.identity] for w in workers})
    uc = ApplyLayoutUseCase(layout=layout, scope_probe=probe, logger=FakeLogger())
    return uc, layout, workers


def test_apply_invokes_a_layout_primitive():
    uc, layout, workers = _build()
    result = uc.apply(COACH_PANE, COACH_WS, workers)
    # At least one real layout mutation was invoked — not zero (print-only).
    assert layout.layout_invocations >= 1
    assert result.layout_invocations >= 1


def test_apply_does_not_succeed_with_zero_port_calls():
    uc, layout, workers = _build()
    uc.apply(COACH_PANE, COACH_WS, workers)
    method_names = {c[0] for c in layout.calls}
    assert method_names & {"create_right_pane", "place_surface_right"}
