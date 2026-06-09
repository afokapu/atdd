"""Pure layout planner + never-collapse specification (issue #865).

The coach-left / workers-right view is window/pane GEOMETRY over per-workspace
surfaces, NOT N workers collapsed into one workspace's tabs. Empirically
(2026-06-09) ``CmuxFeedSource._resolve_scope()`` UNIONS every surface in a
workspace into one daemon scope, so two workers sharing a workspace cross-decide
by construction (#1013). Each worker is therefore its OWN cmux workspace, and the
layout is a workspace-ordering pass (``reorder-workspace --after``): every op
positions a worker's own workspace right of an anchor without ever migrating a
surface into another workspace. A plan over workers that already share a workspace
(or share the coach's) is rejected as a scope collapse.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


class ScopeCollapseError(ValueError):
    """Raised when a layout would make two workers share one daemon scope."""


@dataclass(frozen=True)
class WorkerSurface:
    """A worker's surface in its OWN single-identity workspace.

    ``identity`` is the per-surface workstream identity (resume_binding
    checkpoint id). ``workspace_id`` is the worker's own workspace — the unit the
    daemon scopes by. Two distinct workers must never share a ``workspace_id``.
    """

    surface_ref: str
    workspace_id: str
    identity: str


@dataclass(frozen=True)
class LayoutOp:
    """Position ``workspace_id`` immediately right of ``anchor_workspace_id`` in
    the operator's window — geometry only; never migrates a surface into another
    workspace."""

    op_type: str  # "position_workspace_right"
    workspace_id: str
    surface_ref: str
    anchor_workspace_id: str


@dataclass(frozen=True)
class LayoutPlan:
    ops: tuple[LayoutOp, ...]


def _reject_collapse(coach_workspace_id: str, workers: Sequence[WorkerSurface]) -> None:
    seen: set[str] = set()
    for w in workers:
        if w.workspace_id == coach_workspace_id:
            raise ScopeCollapseError(
                f"worker {w.identity!r} shares the coach workspace "
                f"{coach_workspace_id!r} — would cross-decide (#1013)"
            )
        if w.workspace_id in seen:
            raise ScopeCollapseError(
                f"two workers share workspace {w.workspace_id!r} — would "
                f"collapse into one daemon scope (#1013)"
            )
        seen.add(w.workspace_id)


def plan_layout(
    coach_workspace_id: str,
    workers: Sequence[WorkerSurface],
) -> LayoutPlan:
    """Build the workspace-ordering plan that tiles each per-workspace worker
    right of the coach.

    Raises :class:`ScopeCollapseError` if any two workers share a workspace_id
    (or share the coach's workspace). Each op chains right of the previous worker
    (first worker anchors on the coach), and every op targets a worker by its own
    workspace_id.
    """
    _reject_collapse(coach_workspace_id, workers)
    ops: list[LayoutOp] = []
    anchor = coach_workspace_id
    for w in workers:
        ops.append(
            LayoutOp(
                op_type="position_workspace_right",
                workspace_id=w.workspace_id,
                surface_ref=w.surface_ref,
                anchor_workspace_id=anchor,
            )
        )
        anchor = w.workspace_id
    return LayoutPlan(ops=tuple(ops))


def assert_never_collapse(
    coach_workspace_id: str,
    observed: Sequence[WorkerSurface],
) -> None:
    """Post-condition: after a layout pass each worker still resolves to its own
    single-identity workspace. Raises :class:`ScopeCollapseError` otherwise."""
    _reject_collapse(coach_workspace_id, observed)


__all__ = [
    "LayoutOp",
    "LayoutPlan",
    "ScopeCollapseError",
    "WorkerSurface",
    "assert_never_collapse",
    "plan_layout",
]
