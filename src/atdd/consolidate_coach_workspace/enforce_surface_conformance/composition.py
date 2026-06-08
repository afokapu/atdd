"""Feature composition root for enforce-surface-conformance (SPEC-CODER-COMP-0004).

``build_apply_layout_use_case`` wires the ApplyLayoutUseCase from a multiplexer
backend: the cmux adapter implements both the MultiplexerLayoutPort and the
SurfaceScopeProbe, and a default stderr-backed ConformanceLogger carries
operator-facing intent. RED stub raises NotImplementedError; GREEN fills it in.
"""
from __future__ import annotations

from typing import Any, Optional

from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.application.apply_layout_use_case import (
    ApplyLayoutUseCase,
)


def build_apply_layout_use_case(
    backend: Any,
    *,
    logger: Optional[Any] = None,
) -> ApplyLayoutUseCase:
    raise NotImplementedError(
        "enforce-surface-conformance: build_apply_layout_use_case (GREEN)"
    )


__all__ = ["build_apply_layout_use_case"]
