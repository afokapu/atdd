"""Apply-layout use case (issue #865).

Builds the pure layout plan, invokes the ``MultiplexerLayoutPort`` for each op
(at LEAST one real backend layout primitive per placement — never a print-only
path), then asserts the never-collapse post-condition via the ``SurfaceScopeProbe``.

RED stub raises NotImplementedError; GREEN fills it in.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.application.ports import (
    ConformanceLogger,
    MultiplexerLayoutPort,
    SurfaceScopeProbe,
)
from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.layout_plan import (
    WorkerSurface,
)


@dataclass(frozen=True)
class LayoutResult:
    """Outcome of an apply pass: how many real layout primitives were invoked."""

    layout_invocations: int
    workspaces_verified: tuple[str, ...]


class ApplyLayoutUseCase:
    def __init__(
        self,
        *,
        layout: MultiplexerLayoutPort,
        scope_probe: SurfaceScopeProbe,
        logger: ConformanceLogger,
    ) -> None:
        self._layout = layout
        self._scope_probe = scope_probe
        self._logger = logger

    def apply(
        self,
        coach_pane: str,
        coach_workspace_id: str,
        workers: Sequence[WorkerSurface],
    ) -> LayoutResult:
        """Apply the geometry plan and verify never-collapse.

        MUST invoke at least one ``MultiplexerLayoutPort`` primitive per placement;
        a layout-target log without a port invocation is the #865 regression and
        is forbidden by E003.
        """
        raise NotImplementedError(
            "enforce-surface-conformance: ApplyLayoutUseCase.apply (GREEN)"
        )


__all__ = ["ApplyLayoutUseCase", "LayoutResult"]
