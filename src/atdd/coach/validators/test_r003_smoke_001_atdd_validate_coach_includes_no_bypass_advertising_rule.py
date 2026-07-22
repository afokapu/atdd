# URN: test:govern-lifecycle:coach-operator-safety-invariants:E068-SMOKE-001-atdd-validate-coach-includes-no-bypass-advertising-rule
# Acceptance: acc:govern-lifecycle:R008-SMOKE-001-atdd-validate-coach-includes-no-bypass-advertising-rule
# WMBT: wmbt:govern-lifecycle:R008
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""R003-SMOKE-001 — the no_bypass_advertising validator is importable and passes against the live CLAUDE.md.

SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure.

After R003 GREEN code lands and CLAUDE.md is sanitized per E022:
  - The validator module atdd.coach.validators.claude_md_validators is importable
  - RULE_ID_NO_BYPASS_ADVERTISING == 'coach.claude_md.no_bypass_advertising'
  - validate_claude_md_no_bypass_advertising(REPO_ROOT / 'CLAUDE.md') returns 0 violations
    (the deployed CLAUDE.md contains zero ATDD_SKIP_* tokens)
"""
from __future__ import annotations

import os
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
    """R003-SMOKE-001: no_bypass_advertising validator is registered and passes against live CLAUDE.md."""
    from atdd.coach.validators.claude_md_validators import (  # noqa: PLC0415
        RULE_ID_NO_BYPASS_ADVERTISING,
        validate_claude_md_no_bypass_advertising,
    )

    # Rule is registered with the canonical ID
    assert RULE_ID_NO_BYPASS_ADVERTISING == _RULE_ID, (
        f"RULE_ID_NO_BYPASS_ADVERTISING is '{RULE_ID_NO_BYPASS_ADVERTISING}', "
        f"expected '{_RULE_ID}'.\n"
        "R003 requires the canonical rule ID to be 'coach.claude_md.no_bypass_advertising'."
    )

    claude_md = REPO_ROOT / "CLAUDE.md"
    assert claude_md.exists(), (
        f"CLAUDE.md not found at {claude_md}. "
        "R003-SMOKE requires the live CLAUDE.md to exist in the repo root."
    )

    violations = validate_claude_md_no_bypass_advertising(claude_md)

    assert violations == 0, (
        f"no_bypass_advertising validator reported {violations} violation(s) against live CLAUDE.md.\n"
        "E022 requires CLAUDE.md to contain zero ATDD_SKIP_* tokens after #867.\n"
        f"Check CLAUDE.md at {claude_md} for any remaining bypass tokens."
    )
