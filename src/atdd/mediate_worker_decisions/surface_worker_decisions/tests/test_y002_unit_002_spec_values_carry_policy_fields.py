# URN: test:mediate-worker-decisions:surface-worker-decisions:Y002-UNIT-002-spec-values-carry-policy-fields
# Acceptance: acc:mediate-worker-decisions:Y002-UNIT-002-spec-values-carry-policy-fields
# WMBT: wmbt:mediate-worker-decisions:Y002
# Phase: RED
# Layer: application
# Assertion: behavioral
"""Y002-UNIT-002 — resolved values load onto the existing DispatchSpec fields.

The resolved surfacing values are field-compatible with the existing
DispatchSpec (no new shared type): permission_mode is a valid DispatchSpec mode
and allowed_tools is the auto_allow set with Bash absent. Proven by loading them
into a real DispatchSpec — the surface the cli-return agent_control path (#969)
reads, per §3.3.
"""
from __future__ import annotations

from pathlib import Path

from atdd.runtime.agent_control import DispatchSpec
from atdd.mediate_worker_decisions.surface_worker_decisions.src.application.resolve_surfacing_values import (
    resolve,
)


def test_spec_values_carry_policy_fields():
    values = resolve("claude")

    spec = DispatchSpec(
        agent_id="a1",
        persona="coder",
        worktree_path=Path("/tmp/wt"),
        prompt_text="hi",
        correction_inbox=Path("/tmp/wt/cli-return.jsonl"),
        output_log=Path("/tmp/wt/output.log"),
        runtime_dir=Path("/tmp/wt/.atdd"),
        env_overrides={},
        transport="cli-return",
        permission_mode=values.permission_mode,
        allowed_tools=values.allowed_tools,
    )

    assert spec.permission_mode == "acceptEdits"
    assert "Bash" not in spec.allowed_tools
