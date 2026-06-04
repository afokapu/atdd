# URN: test:mediate-worker-decisions:surface-worker-decisions:C006-UNIT-001-no-bypass-and-bash-always-surfaced
# Acceptance: acc:mediate-worker-decisions:C006-UNIT-001-no-bypass-and-bash-always-surfaced
# WMBT: wmbt:mediate-worker-decisions:C006
# Phase: RED
# Layer: application
# Assertion: behavioral
"""C006-UNIT-001 — no rendered config bypasses surfacing, for any claude agent kind.

Every supported claude-family worker's resolved values omit the forbidden bypass
flags/modes and never list Bash in allowed_tools, so an action-class decision can
never execute without first surfacing to the Feed.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.surface_worker_decisions.src.application.resolve_surfacing_values import (
    resolve,
)
from atdd.mediate_worker_decisions.surface_worker_decisions.src.domain.decision_surfacing_policy import (
    BYPASS_PERMISSION_MODES,
    FORBIDDEN_FLAGS,
)
from atdd.mediate_worker_decisions.surface_worker_decisions.tests._helpers import (
    CLAUDE_AGENT_KINDS,
)


def test_no_bypass_and_bash_always_surfaced():
    for kind in CLAUDE_AGENT_KINDS:
        values = resolve(kind)

        assert values.permission_mode not in BYPASS_PERMISSION_MODES, kind
        assert "Bash" not in values.allowed_tools, kind
        # No forbidden flag may appear among the rendered tool tokens.
        for flag in FORBIDDEN_FLAGS:
            assert flag not in values.allowed_tools, (kind, flag)
