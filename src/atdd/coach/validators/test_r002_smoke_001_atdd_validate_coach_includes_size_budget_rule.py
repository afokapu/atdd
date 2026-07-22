# URN: test:govern-lifecycle:coach-operator-safety-invariants:E067-SMOKE-001-atdd-validate-coach-includes-size-budget-rule
# Acceptance: acc:govern-lifecycle:R007-SMOKE-001-atdd-validate-coach-includes-size-budget-rule
# WMBT: wmbt:govern-lifecycle:R007
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""R002-SMOKE-001 — the size_budget validator is importable and passes against the live CLAUDE.md.

SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure.

After R002 GREEN code lands and CLAUDE.md is slimmed per E023:
  - The validator module atdd.coach.validators.claude_md_validators is importable
  - RULE_ID_SIZE_BUDGET == 'coach.claude_md.size_budget' (rule is registered)
  - validate_claude_md_size_budget(REPO_ROOT / 'CLAUDE.md') returns 0 violations
    (the deployed CLAUDE.md is within the 250-line context budget)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
_RULE_ID = "coach.claude_md.size_budget"
_LINE_BUDGET = 250


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_atdd_validate_coach_includes_size_budget_rule():
    """R002-SMOKE-001: size_budget validator is registered and passes against live CLAUDE.md."""
    from atdd.coach.validators.claude_md_validators import (  # noqa: PLC0415
        RULE_ID_SIZE_BUDGET,
        validate_claude_md_size_budget,
    )

    # Rule is registered with the canonical ID
    assert RULE_ID_SIZE_BUDGET == _RULE_ID, (
        f"RULE_ID_SIZE_BUDGET is '{RULE_ID_SIZE_BUDGET}', expected '{_RULE_ID}'.\n"
        "R002 requires the canonical rule ID to be 'coach.claude_md.size_budget'."
    )

    claude_md = REPO_ROOT / "CLAUDE.md"
    assert claude_md.exists(), (
        f"CLAUDE.md not found at {claude_md}. "
        "R002-SMOKE requires the live CLAUDE.md to exist in the repo root."
    )

    line_count = len(claude_md.read_text(encoding="utf-8").splitlines())
    violations = validate_claude_md_size_budget(claude_md)

    assert violations == 0, (
        f"size_budget validator reported {violations} violation(s) against live CLAUDE.md.\n"
        f"CLAUDE.md has {line_count} lines (budget: {_LINE_BUDGET}).\n"
        "E023 requires CLAUDE.md to be ≤ 250 lines after #867."
    )
