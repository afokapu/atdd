"""Presentation entrypoints — the thin delegation targets for the flat-wagon shim.

``session_naming_apply.apply_canonical_name_and_layout`` (the flat seam) delegates
to :func:`place_worker_surface_right` for a single spawned surface; the coach-level
multi-worker pass uses :func:`apply_surface_conformance`. Both invoke a REAL cmux
layout primitive through the composition root, so the conformance pass can no
longer ship a no-op print of the layout label (issue #865).
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from atdd.consolidate_coach_workspace.enforce_surface_conformance.composition import (
    build_apply_layout_use_case,
)
from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.application.apply_layout_use_case import (
    LayoutResult,
)
from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.layout_plan import (
    WorkerSurface,
)


def apply_surface_conformance(
    backend: Any,
    *,
    coach_pane: str,
    coach_workspace_id: str,
    workers: Sequence[WorkerSurface],
    logger: Optional[Any] = None,
) -> LayoutResult:
    """Run the multi-worker layout conformance pass (coach-left / workers-right
    geometry over per-workspace surfaces) and verify never-collapse."""
    use_case = build_apply_layout_use_case(backend, logger=logger)
    return use_case.apply(coach_pane, coach_workspace_id, workers)


def place_worker_surface_right(
    backend: Any,
    surface_ref: str,
    *,
    anchor_workspace_id: Optional[str] = None,
    logger: Optional[Any] = None,
) -> LayoutResult:
    """Single-surface layout pass for a freshly-spawned worker (the shim's target).

    Resolves the surface's own workspace and positions it right of the anchor (the
    coach / current workspace) via a real cmux layout primitive — never migrating
    the surface into another workspace."""
    workspace_id = backend.surface_workspace(surface_ref)
    anchor = anchor_workspace_id or backend.current_workspace()
    worker = WorkerSurface(
        surface_ref=surface_ref, workspace_id=workspace_id, identity=surface_ref
    )
    use_case = build_apply_layout_use_case(backend, logger=logger)
    return use_case.apply(anchor, anchor, [worker])


__all__ = ["apply_surface_conformance", "place_worker_surface_right"]
