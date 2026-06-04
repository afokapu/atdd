# URN: test:mediate-worker-decisions:surface-worker-decisions:C005-INTEGRATION-001-policy-rejects-forbidden-flag
# Acceptance: acc:mediate-worker-decisions:C005-INTEGRATION-001-policy-rejects-forbidden-flag
# WMBT: wmbt:mediate-worker-decisions:C005
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C005-INTEGRATION-001 — a surfacing-suppressing policy is rejected at build time.

Building a DecisionSurfacingPolicy that auto-allows an action-class tool (Bash) or
sets a bypass permission_mode raises PolicyError — it is never silently rendered.
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.surface_worker_decisions.src.domain.decision_surfacing_policy import (
    DecisionSurfacingPolicy,
    PolicyError,
)
from atdd.mediate_worker_decisions.surface_worker_decisions.src.domain.surfacing_renderer import (
    to_dispatch_values,
)


def test_bash_in_auto_allow_is_rejected():
    bad = DecisionSurfacingPolicy(
        agent_kind="claude",
        permission_mode="acceptEdits",
        auto_allow_tools=("Read", "Bash"),  # action-class tool must never auto-allow
        surface_tools=("Bash",),
    )
    with pytest.raises(PolicyError):
        to_dispatch_values(bad)


def test_bypass_permission_mode_is_rejected():
    bad = DecisionSurfacingPolicy(
        agent_kind="claude",
        permission_mode="bypassPermissions",  # suppresses every PermissionRequest
        auto_allow_tools=("Read", "Edit"),
        surface_tools=("Bash",),
    )
    with pytest.raises(PolicyError):
        to_dispatch_values(bad)
