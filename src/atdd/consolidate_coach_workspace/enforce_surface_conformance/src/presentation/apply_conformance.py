"""Presentation entrypoint — the thin delegation target for the flat-wagon shim.

``session_naming_apply.apply_canonical_name_and_layout`` (the flat seam) delegates
here. This applies the role-aware rename and invokes the real layout pass through
the composition root, so the function can no longer ship a no-op print of the
layout label.

RED stub raises NotImplementedError; GREEN fills it in.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

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
) -> Any:
    """Run the layout conformance pass for the given per-workspace workers.

    Builds the cmux adapter + use case from ``backend`` (via the composition root)
    and applies the geometry plan, invoking a real backend layout primitive.
    Returns the ``LayoutResult``.
    """
    raise NotImplementedError(
        "enforce-surface-conformance: apply_surface_conformance (GREEN)"
    )


__all__ = ["apply_surface_conformance"]
