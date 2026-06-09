"""Feature composition root for enforce-surface-conformance (SPEC-CODER-COMP-0004).

``build_apply_layout_use_case`` wires the ApplyLayoutUseCase from a multiplexer
backend: a single CmuxLayoutAdapter implements both the MultiplexerLayoutPort and
the SurfaceScopeProbe, and a default stderr-backed ConformanceLogger carries
operator-facing intent (distinct from a layout invocation).
"""
from __future__ import annotations

import sys
from typing import Any, Optional

from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.application.apply_layout_use_case import (
    ApplyLayoutUseCase,
)
from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.integration.cmux_layout_adapter import (
    CmuxLayoutAdapter,
)


class _StderrConformanceLogger:
    """Default operator-facing logger — writes the conformance intent to stderr."""

    def emit(self, message: str, *, rule_id: str) -> None:
        print(f"   {message} ({rule_id})", file=sys.stderr)


def build_apply_layout_use_case(
    backend: Any,
    *,
    logger: Optional[Any] = None,
) -> ApplyLayoutUseCase:
    adapter = CmuxLayoutAdapter(backend)
    return ApplyLayoutUseCase(
        layout=adapter,
        scope_probe=adapter,
        logger=logger or _StderrConformanceLogger(),
    )


__all__ = ["build_apply_layout_use_case"]
