"""Pure layout planner + never-collapse specification (issue #865).

The coach-left / workers-right view is window/pane GEOMETRY over per-workspace
surfaces, NOT N workers collapsed into one workspace's tabs. Empirically
(2026-06-09) ``CmuxFeedSource._resolve_scope()`` UNIONS every surface in a
workspace into one daemon scope, so two workers sharing a workspace cross-decide
by construction (#1013). This planner therefore refuses to emit any op that would
move a worker surface out of its own single-identity workspace: each op references
a worker BY its own workspace, and a plan over workers that already share a
workspace is rejected as a scope collapse.

RED stubs raise NotImplementedError; GREEN fills them in.
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
    """A single geometry mutation: place a worker's own surface in the right
    region of the operator's view WITHOUT migrating it into another workspace."""

    op_type: str  # "create_right_pane" | "place_surface_right"
    workspace_id: str
    surface_ref: str


@dataclass(frozen=True)
class LayoutPlan:
    ops: tuple[LayoutOp, ...]


def plan_layout(
    coach_workspace_id: str,
    workers: Sequence[WorkerSurface],
) -> LayoutPlan:
    """Build the geometry plan that tiles each per-workspace worker on the right.

    Raises :class:`ScopeCollapseError` if any two workers share a workspace_id
    (or share the coach's workspace) — that would collapse two identities into
    one daemon scope. Every emitted op targets a worker by its own workspace_id.
    """
    raise NotImplementedError("enforce-surface-conformance: plan_layout (GREEN)")


def assert_never_collapse(
    coach_workspace_id: str,
    workers: Sequence[WorkerSurface],
) -> None:
    """Post-condition check: after a layout pass each worker still resolves to
    its own single-identity workspace. Raises :class:`ScopeCollapseError`
    otherwise. Pure: operates on the observed (workspace_id, identity) tuples."""
    raise NotImplementedError(
        "enforce-surface-conformance: assert_never_collapse (GREEN)"
    )


__all__ = [
    "LayoutOp",
    "LayoutPlan",
    "ScopeCollapseError",
    "WorkerSurface",
    "assert_never_collapse",
    "plan_layout",
]
