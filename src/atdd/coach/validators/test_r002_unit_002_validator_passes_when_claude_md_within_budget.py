# URN: test:govern-lifecycle:coach-operator-safety-invariants:E067-UNIT-002-validator-passes-when-claude-md-within-budget
# Acceptance: acc:govern-lifecycle:R007-UNIT-002-validator-passes-when-claude-md-within-budget
# WMBT: wmbt:govern-lifecycle:R007
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral
"""R002-UNIT-002 — coach.claude_md.size_budget validator passes for ≤ 250 lines.

Phase RED: fails — the validator module
    atdd.coach.validators.claude_md_validators
does not exist yet; importing raises ImportError.

Phase GREEN: validate_claude_md_size_budget(path) returns 0 violations when
the file has exactly 250 lines (the budget boundary).
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

_LINE_BUDGET = 250


def test_size_budget_validator_passes_for_exactly_250_lines(tmp_path: Path):
    """R002-UNIT-002: validator returns 0 violations when CLAUDE.md has exactly 250 lines."""
    # Deferred import — fails with ImportError in RED (validator not yet created)
    from atdd.coach.validators.claude_md_validators import (  # noqa: PLC0415
        validate_claude_md_size_budget,
    )

    at_budget = tmp_path / "CLAUDE.md"
    at_budget.write_text("\n".join(["line"] * _LINE_BUDGET), encoding="utf-8")

    result = validate_claude_md_size_budget(at_budget)

    assert isinstance(result, int), (
        f"validate_claude_md_size_budget should return an int violation count, "
        f"got {type(result).__name__}"
    )
    assert result == 0, (
        f"validate_claude_md_size_budget returned {result} violations for a "
        f"{_LINE_BUDGET}-line file — expected 0 (within budget).\n"
        "Rule: coach.claude_md.size_budget must pass (0 violations) when "
        f"line count ≤ {_LINE_BUDGET}."
    )


def test_size_budget_validator_passes_for_250_minus_one_lines(tmp_path: Path):
    """R002-UNIT-002 (boundary): validator passes for 249 lines (under budget)."""
    from atdd.coach.validators.claude_md_validators import (  # noqa: PLC0415
        validate_claude_md_size_budget,
    )

    under_budget = tmp_path / "CLAUDE.md"
    under_budget.write_text("\n".join(["line"] * (_LINE_BUDGET - 1)), encoding="utf-8")

    result = validate_claude_md_size_budget(under_budget)
    assert result == 0, (
        f"validate_claude_md_size_budget returned {result} violations for a "
        f"{_LINE_BUDGET - 1}-line file — expected 0 (under budget)."
    )
