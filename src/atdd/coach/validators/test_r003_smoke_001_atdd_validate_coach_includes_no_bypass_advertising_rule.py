# URN: test:spawn-agents:claude-md-slim-and-debanner:R003-SMOKE-001-atdd-validate-coach-includes-no-bypass-advertising-rule
# Acceptance: acc:spawn-agents:R003-SMOKE-001-atdd-validate-coach-includes-no-bypass-advertising-rule
# WMBT: wmbt:spawn-agents:R003
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""R003-SMOKE-001 — `atdd validate coach` includes the no_bypass_advertising rule and it passes.

SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure.

After R003 GREEN code lands and CLAUDE.md is sanitized per E022:
  - atdd validate coach completes without error
  - The rule ID 'coach.claude_md.no_bypass_advertising' appears in the output
  - No no_bypass_advertising violation is reported (CLAUDE.md has zero bypass tokens)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
_RULE_ID = "coach.claude_md.no_bypass_advertising"


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_atdd_validate_coach_includes_no_bypass_advertising_rule():
    """R003-SMOKE-001: atdd validate coach runs no_bypass_advertising rule with 0 violations."""
    result = subprocess.run(
        ["atdd", "validate", "coach", "--local", "--skip-api"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    output = result.stdout + result.stderr

    assert _RULE_ID in output, (
        f"Rule ID '{_RULE_ID}' not found in `atdd validate coach` output.\n"
        "R003 requires the no_bypass_advertising validator to be registered in "
        "the coach validator suite and to emit its rule ID on each run.\n"
        f"Full output:\n{output}"
    )

    # Return code 0 confirms no violations were detected
    assert result.returncode == 0, (
        f"`atdd validate coach` exited with code {result.returncode} — "
        "a no_bypass_advertising violation may have been reported.\n"
        "Ensure CLAUDE.md contains zero ATDD_SKIP_* tokens (E022 prerequisite).\n"
        f"Output:\n{output}"
    )
