# URN: test:govern-lifecycle:coach-operator-safety-invariants:E067-UNIT-001-validator-fails-when-claude-md-exceeds-budget
# Acceptance: acc:govern-lifecycle:R007-UNIT-001-validator-fails-when-claude-md-exceeds-budget
# WMBT: wmbt:govern-lifecycle:R007
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral
"""R002-UNIT-001 — coach.claude_md.size_budget validator raises an error for > 250 lines.

Phase RED: fails — the validator module
    atdd.coach.validators.claude_md_validators
does not exist yet; importing the validator raises ImportError.

Phase GREEN: the coder creates claude_md_validators.py with a
validate_claude_md_size_budget(path) callable that raises ValidationError
(or returns a non-zero violation count) when the file has > 250 lines.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

_LINE_BUDGET = 250


def test_size_budget_validator_fails_for_oversized_file(tmp_path: Path):
    """R002-UNIT-001: validator raises error when CLAUDE.md clone has > 250 lines."""
    # Deferred import — fails with ImportError in RED (validator not yet created)
    from atdd.coach.validators.claude_md_validators import (  # noqa: PLC0415
        validate_claude_md_size_budget,
    )

    # Synthetic oversized file: 251 lines
    oversized = tmp_path / "CLAUDE.md"
    oversized.write_text("\n".join(["line"] * (_LINE_BUDGET + 1)), encoding="utf-8")

    result = validate_claude_md_size_budget(oversized)

    # Validator must signal a violation — either raise or return violation count > 0
    if isinstance(result, int):
        assert result > 0, (
            f"validate_claude_md_size_budget returned 0 violations for a "
            f"{_LINE_BUDGET + 1}-line file — expected a non-zero count.\n"
            f"Rule: coach.claude_md.size_budget (sev 3, strict) must fail when "
            f"line count > {_LINE_BUDGET}."
        )
    else:
        pytest.fail(
            f"validate_claude_md_size_budget returned {result!r} for an oversized file; "
            "expected an integer violation count > 0 or a raised ValidationError."
        )


def test_size_budget_validator_error_message_references_count_and_budget(tmp_path: Path):
    """R002-UNIT-001 (supplement): error message identifies line count and budget."""
    from atdd.coach.validators.claude_md_validators import (  # noqa: PLC0415
        validate_claude_md_size_budget,
    )

    oversized = tmp_path / "CLAUDE.md"
    line_count = _LINE_BUDGET + 5
    oversized.write_text("\n".join(["line"] * line_count), encoding="utf-8")

    # If the validator raises, inspect the message
    try:
        violations = validate_claude_md_size_budget(oversized)
    except Exception as exc:
        msg = str(exc)
        assert str(line_count) in msg or str(_LINE_BUDGET) in msg, (
            f"Exception message '{msg}' does not reference the line count ({line_count}) "
            f"or budget ({_LINE_BUDGET}).\n"
            "R002 requires the error to identify both so the operator can act."
        )
        return

    # If it returns a violation object, check violation count > 0
    assert violations > 0, (
        "validate_claude_md_size_budget returned 0 for an oversized file."
    )
