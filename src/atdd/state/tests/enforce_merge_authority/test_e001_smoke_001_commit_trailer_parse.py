# URN: test:enforce-merge-authority:parse-commit-trailer:E001-SMOKE-001-commit-trailer-parse
# Acceptance: acc:enforce-merge-authority:E001-SMOKE-001-commit-trailer-parse
# WMBT: wmbt:enforce-merge-authority:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:E001-SMOKE-001-commit-trailer-parse — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:E001-SMOKE-001-commit-trailer-parse.

wagon: enforce-merge-authority | feature: parse-commit-trailer | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (commit-trailer-parse holds end-to-end against a real commit message and CLI). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_e001_smoke_001_commit_trailer_parse(tmp_path) -> None:
    """E001-SMOKE-001-commit-trailer-parse — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:E001-SMOKE-001-commit-trailer-parse is not implemented yet"
    )
