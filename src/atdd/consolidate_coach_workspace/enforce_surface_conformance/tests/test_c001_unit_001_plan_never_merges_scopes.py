# URN: test:consolidate-coach-workspace:enforce-surface-conformance:C001-UNIT-001-plan-never-merges-scopes
# Acceptance: acc:consolidate-coach-workspace:C001-UNIT-001-plan-never-merges-scopes
# WMBT: wmbt:consolidate-coach-workspace:C001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C001-UNIT-001 — the pure layout planner never merges two workers into one
daemon scope. Every op targets a worker by its own workspace; a plan over workers
that already share a workspace is rejected (the #1013 _resolve_scope union hazard
made impossible at the plan level)."""
from __future__ import annotations

import pytest

from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.layout_plan import (
    ScopeCollapseError,
    WorkerSurface,
    plan_layout,
)

COACH_WS = "workspace:coach"


def _worker(n: int) -> WorkerSurface:
    return WorkerSurface(
        surface_ref=f"surface:{n}",
        workspace_id=f"workspace:{n}",
        identity=f"claude-{n}",
    )


def test_plan_targets_each_worker_by_its_own_workspace():
    workers = [_worker(1), _worker(2), _worker(3)]
    plan = plan_layout(COACH_WS, workers)

    worker_ws = {w.workspace_id for w in workers}
    op_ws = {op.workspace_id for op in plan.ops}
    # Every op stays inside a worker's OWN workspace; none touches the coach's.
    assert op_ws <= worker_ws
    assert COACH_WS not in op_ws
    # Each worker's surface is placed (geometry over per-workspace surfaces).
    placed = {op.surface_ref for op in plan.ops}
    assert {w.surface_ref for w in workers} <= placed


def test_plan_rejects_two_workers_sharing_a_workspace():
    collapsing = [
        WorkerSurface("surface:1", "workspace:shared", "claude-1"),
        WorkerSurface("surface:2", "workspace:shared", "claude-2"),
    ]
    with pytest.raises(ScopeCollapseError):
        plan_layout(COACH_WS, collapsing)


def test_plan_rejects_worker_sharing_the_coach_workspace():
    collapsing = [WorkerSurface("surface:1", COACH_WS, "claude-1")]
    with pytest.raises(ScopeCollapseError):
        plan_layout(COACH_WS, collapsing)
