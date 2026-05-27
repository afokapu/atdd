# URN: test:spawn-agents:claude-md-slim-and-debanner:R002-SMOKE-001-atdd-validate-coach-includes-size-budget-rule
# Acceptance: acc:spawn-agents:R002-SMOKE-001-atdd-validate-coach-includes-size-budget-rule
# WMBT: wmbt:spawn-agents:R002
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""R002-SMOKE-001 — `atdd validate coach` includes the size_budget rule and it passes.

SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure.

After R002 GREEN code lands and CLAUDE.md is slimmed per E023:
  - atdd validate coach completes without error
  - The rule ID 'coach.claude_md.size_budget' appears in the validator output
  - No size_budget violation is reported (CLAUDE.md is within the 250-line budget)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
_RULE_ID = "coach.claude_md.size_budget"


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_atdd_validate_coach_includes_size_budget_rule():
    """R002-SMOKE-001: atdd validate coach runs size_budget rule with 0 violations."""
    result = subprocess.run(
        ["atdd", "validate", "coach", "--local", "--skip-api"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    output = result.stdout + result.stderr

    assert _RULE_ID in output, (
        f"Rule ID '{_RULE_ID}' not found in `atdd validate coach` output.\n"
        "R002 requires the size_budget validator to be registered in the coach "
        "validator suite and to emit its rule ID on each run.\n"
        f"Full output:\n{output}"
    )

    # Should not report a violation since CLAUDE.md was slimmed per E023
    assert "size_budget" not in output.lower().split("violation")[0] or result.returncode == 0, (
        f"`atdd validate coach` reported a size_budget violation — "
        "CLAUDE.md may not have been slimmed to ≤ 250 lines yet.\n"
        f"Return code: {result.returncode}\nOutput:\n{output}"
    )
