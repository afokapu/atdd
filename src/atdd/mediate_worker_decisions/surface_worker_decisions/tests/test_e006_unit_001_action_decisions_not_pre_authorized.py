# URN: test:mediate-worker-decisions:surface-worker-decisions:E006-UNIT-001-action-decisions-not-pre-authorized
# Acceptance: acc:mediate-worker-decisions:E006-UNIT-001-action-decisions-not-pre-authorized
# WMBT: wmbt:mediate-worker-decisions:E006
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E006-UNIT-001 — resolving surfacing values leaves action-class decisions un-allowed.

Resolving the surfacing values for a claude worker yields allowed_tools that
auto-allow the read/edit tools but NOT Bash, under permission_mode acceptEdits and
with no bypass flag — so a Bash / AskUserQuestion / ExitPlanMode decision still
raises a PermissionRequest and reaches the Feed.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.surface_worker_decisions.src.application.resolve_surfacing_values import (
    resolve,
)


def test_action_decisions_not_pre_authorized():
    values = resolve("claude")

    # acceptEdits keeps edits frictionless without suppressing permission prompts.
    assert values.permission_mode == "acceptEdits"
    # Read/edit tools are auto-allowed for autonomy...
    assert "Read" in values.allowed_tools
    assert "Edit" in values.allowed_tools
    # ...but the action-class decision tool is deliberately NOT pre-authorized.
    assert "Bash" not in values.allowed_tools
