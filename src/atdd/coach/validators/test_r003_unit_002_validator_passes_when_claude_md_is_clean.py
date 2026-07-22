# URN: test:govern-lifecycle:coach-operator-safety-invariants:E068-UNIT-002-validator-passes-when-claude-md-is-clean
# Acceptance: acc:govern-lifecycle:R008-UNIT-002-validator-passes-when-claude-md-is-clean
# WMBT: wmbt:govern-lifecycle:R008
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral
"""R003-UNIT-002 — coach.claude_md.no_bypass_advertising validator passes for clean content.

Phase RED: fails — the validator module
    atdd.coach.validators.claude_md_validators
does not exist yet; importing raises ImportError.

Phase GREEN: validate_claude_md_no_bypass_advertising(path) returns 0 violations
when CLAUDE.md has no ATDD_SKIP_* or --no-verify tokens.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]


def test_bypass_advertising_validator_passes_for_clean_file(tmp_path: Path):
    """R003-UNIT-002: validator returns 0 for CLAUDE.md with no bypass tokens."""
    # Deferred import — fails with ImportError in RED (validator not yet created)
    from atdd.coach.validators.claude_md_validators import (  # noqa: PLC0415
        validate_claude_md_no_bypass_advertising,
    )

    clean = tmp_path / "CLAUDE.md"
    clean.write_text(
        "# CLAUDE.md — clean content\n\n"
        "## ATDD Lifecycle\n\n"
        "For emergencies: see docs/operator-emergency-bypass.md\n"
        "  Run: atdd emergency --reason '<reason>'\n\n"
        "## Phases\n\n"
        "INIT → PLANNED → RED → GREEN → SMOKE → REFACTOR\n",
        encoding="utf-8",
    )

    result = validate_claude_md_no_bypass_advertising(clean)

    assert isinstance(result, int), (
        f"validate_claude_md_no_bypass_advertising should return an int, "
        f"got {type(result).__name__}"
    )
    assert result == 0, (
        f"validate_claude_md_no_bypass_advertising returned {result} violations "
        "for a clean CLAUDE.md — expected 0.\n"
        "Rule: coach.claude_md.no_bypass_advertising must pass (0 violations) "
        "when no bypass tokens are present."
    )


def test_bypass_advertising_validator_tolerates_cli_form_in_clean_content(tmp_path: Path):
    """R003-UNIT-002 (boundary): 'atdd emergency --reason' in content is NOT a violation."""
    from atdd.coach.validators.claude_md_validators import (  # noqa: PLC0415
        validate_claude_md_no_bypass_advertising,
    )

    # The CLI form is the CORRECT reference; should not be flagged
    clean = tmp_path / "CLAUDE.md"
    clean.write_text(
        "Emergency override: atdd emergency --reason '<reason>'\n"
        "Creates: .atdd/EMERGENCY_BYPASS with 5-minute TTL\n",
        encoding="utf-8",
    )

    result = validate_claude_md_no_bypass_advertising(clean)
    assert result == 0, (
        f"Validator flagged {result} violation(s) for content with only the CLI "
        "form 'atdd emergency' — the CLI form must NOT be treated as a bypass token."
    )
