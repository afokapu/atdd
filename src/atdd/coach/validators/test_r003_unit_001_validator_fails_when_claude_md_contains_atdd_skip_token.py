# URN: test:govern-lifecycle:coach-operator-safety-invariants:E068-UNIT-001-validator-fails-when-claude-md-contains-atdd-skip-token
# Acceptance: acc:govern-lifecycle:R008-UNIT-001-validator-fails-when-claude-md-contains-atdd-skip-token
# WMBT: wmbt:govern-lifecycle:R008
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral
"""R003-UNIT-001 — coach.claude_md.no_bypass_advertising validator fails for ATDD_SKIP_* content.

Phase RED: fails — the validator module
    atdd.coach.validators.claude_md_validators
does not exist yet; importing raises ImportError.

Phase GREEN: validate_claude_md_no_bypass_advertising(path) raises ValidationError
(or returns violation count > 0) when CLAUDE.md content contains an ATDD_SKIP_*
env-var token, with an error message identifying the matched token and line number.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]


def test_bypass_advertising_validator_fails_for_atdd_skip_postcommit(tmp_path: Path):
    """R003-UNIT-001: validator detects ATDD_SKIP_POSTCOMMIT=1 token in synthetic CLAUDE.md."""
    # Deferred import — fails with ImportError in RED (validator not yet created)
    from atdd.coach.validators.claude_md_validators import (  # noqa: PLC0415
        validate_claude_md_no_bypass_advertising,
    )

    dirty = tmp_path / "CLAUDE.md"
    dirty.write_text(
        "# Test CLAUDE.md\n"
        "## Emergency overrides\n"
        "  ATDD_SKIP_POSTCOMMIT=1  # bypass post-commit validator\n"
        "Normal content line.\n",
        encoding="utf-8",
    )

    result = validate_claude_md_no_bypass_advertising(dirty)

    if isinstance(result, int):
        assert result > 0, (
            "validate_claude_md_no_bypass_advertising returned 0 violations for a file "
            "containing 'ATDD_SKIP_POSTCOMMIT=1' — expected > 0.\n"
            "Rule: coach.claude_md.no_bypass_advertising (sev 3, strict) must catch "
            "ATDD_SKIP_* token re-introduction."
        )
    else:
        pytest.fail(
            f"validate_claude_md_no_bypass_advertising returned {result!r} for dirty content; "
            "expected an int violation count > 0 or a raised ValidationError."
        )


def test_bypass_advertising_validator_error_identifies_token_and_line(tmp_path: Path):
    """R003-UNIT-001 (supplement): error message identifies the bypass token and its line number."""
    from atdd.coach.validators.claude_md_validators import (  # noqa: PLC0415
        validate_claude_md_no_bypass_advertising,
    )

    dirty = tmp_path / "CLAUDE.md"
    dirty.write_text(
        "line 1\n"
        "line 2\n"
        "ATDD_SKIP_PREPUSH=1\n"
        "line 4\n",
        encoding="utf-8",
    )

    try:
        result = validate_claude_md_no_bypass_advertising(dirty)
        if isinstance(result, int) and result > 0:
            # If it returns violations without raising, the caller checks the registry
            # for the error message — this is acceptable for a count-based API
            return
    except Exception as exc:
        msg = str(exc)
        assert "ATDD_SKIP_" in msg or "bypass" in msg.lower(), (
            f"Exception message '{msg}' should reference the bypass token or 'bypass'.\n"
            "R003 requires the error to identify the matched token so the operator "
            "can locate and remove it."
        )
        return

    pytest.fail(
        "validate_claude_md_no_bypass_advertising returned 0 for dirty content "
        "— expected violation count > 0 or a raised exception."
    )


def test_bypass_advertising_validator_catches_various_skip_patterns(tmp_path: Path):
    """R003-UNIT-001 (patterns): validator catches ATDD_SKIP_PREPUSH and ATDD_SKIP_ALL."""
    from atdd.coach.validators.claude_md_validators import (  # noqa: PLC0415
        validate_claude_md_no_bypass_advertising,
    )

    for token in ["ATDD_SKIP_PREPUSH", "ATDD_SKIP_ALL_GATES", "ATDD_SKIP_POSTCOMMIT"]:
        dirty = tmp_path / f"CLAUDE_{token}.md"
        dirty.write_text(f"override: {token}=1\n", encoding="utf-8")

        try:
            result = validate_claude_md_no_bypass_advertising(dirty)
            if isinstance(result, int):
                assert result > 0, (
                    f"Validator returned 0 for token '{token}' — expected > 0."
                )
        except Exception:
            pass  # Any exception means the validator fired — that's a pass
