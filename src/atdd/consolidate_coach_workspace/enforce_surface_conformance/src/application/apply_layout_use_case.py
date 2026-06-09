"""Apply-layout use case (issue #865).

Builds the pure layout plan, invokes the ``MultiplexerLayoutPort`` for each op
(at LEAST one real backend layout primitive per worker — never a print-only path),
then asserts the never-collapse post-condition via the ``SurfaceScopeProbe``: each
worker's workspace must still resolve to exactly one identity after the pass.
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
    ScopeCollapseError,
    WorkerSurface,
    plan_layout,
)

LAYOUT_RULE_ID = "coach.session.layout-conformance"


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

        Invokes one ``MultiplexerLayoutPort.position_workspace_right`` per worker;
        a layout-target log without a port invocation is the #865 regression and
        cannot satisfy this method.
        """
        plan = plan_layout(coach_workspace_id, workers)

        self._logger.emit(
            f"layout: {len(plan.ops)} worker workspace(s) right of coach "
            f"{coach_workspace_id}",
            rule_id=LAYOUT_RULE_ID,
        )

        invocations = 0
        for op in plan.ops:
            self._layout.position_workspace_right(
                op.workspace_id, anchor_workspace_id=op.anchor_workspace_id
            )
            invocations += 1

        # Never-collapse post-condition against LIVE state: every worker
        # workspace still resolves to exactly one identity, all distinct.
        verified: list[str] = []
        seen_identities: set[str] = set()
        for w in workers:
            ids = self._scope_probe.list_identities(w.workspace_id)
            if len(ids) != 1:
                raise ScopeCollapseError(
                    f"workspace {w.workspace_id!r} holds {len(ids)} identities "
                    f"after layout — never-collapse violated (#865/#1013): {ids}"
                )
            (only,) = ids
            if only in seen_identities:
                raise ScopeCollapseError(
                    f"identity {only!r} appears in more than one workspace after "
                    f"layout — scope collapse (#865/#1013)"
                )
            seen_identities.add(only)
            verified.append(w.workspace_id)

        return LayoutResult(
            layout_invocations=invocations,
            workspaces_verified=tuple(verified),
        )


__all__ = ["ApplyLayoutUseCase", "LayoutResult", "LAYOUT_RULE_ID"]
