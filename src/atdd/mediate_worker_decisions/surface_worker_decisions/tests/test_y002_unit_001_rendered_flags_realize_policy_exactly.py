# URN: test:mediate-worker-decisions:surface-worker-decisions:Y002-UNIT-001-rendered-flags-realize-policy-exactly
# Acceptance: acc:mediate-worker-decisions:Y002-UNIT-001-rendered-flags-realize-policy-exactly
# WMBT: wmbt:mediate-worker-decisions:Y002
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""Y002-UNIT-001 — the renderer is the exact image of the policy.

Rendering a DecisionSurfacingPolicy to DispatchSpec values yields allowed_tools
equal to the policy auto_allow set (no extras, none missing), a surface set
disjoint from allowed_tools, and permission_mode equal to the policy mode.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.surface_worker_decisions.src.domain.decision_surfacing_policy import (
    DecisionSurfacingPolicy,
)
from atdd.mediate_worker_decisions.surface_worker_decisions.src.domain.surfacing_renderer import (
    to_dispatch_values,
)


def test_rendered_flags_realize_policy_exactly():
    policy = DecisionSurfacingPolicy(
        agent_kind="claude",
        permission_mode="acceptEdits",
        auto_allow_tools=("Read", "Edit", "Write", "Glob"),
        surface_tools=("Bash",),
    )

    values = to_dispatch_values(policy)

    assert set(values.allowed_tools) == set(policy.auto_allow_tools)
    assert set(values.allowed_tools).isdisjoint(policy.surface_tools)
    assert values.permission_mode == policy.permission_mode
