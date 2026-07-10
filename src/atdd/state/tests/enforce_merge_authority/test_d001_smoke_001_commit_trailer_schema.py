# URN: test:enforce-merge-authority:parse-commit-trailer:D001-SMOKE-001-commit-trailer-schema
# Acceptance: acc:enforce-merge-authority:D001-SMOKE-001-commit-trailer-schema
# WMBT: wmbt:enforce-merge-authority:D001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:D001-SMOKE-001-commit-trailer-schema — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:D001-SMOKE-001-commit-trailer-schema.

wagon: enforce-merge-authority | feature: parse-commit-trailer | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:D001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (commit-trailer-schema holds end-to-end against real infrastructure). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_d001_smoke_001_commit_trailer_schema(tmp_path) -> None:
    """D001-SMOKE-001-commit-trailer-schema — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:D001-SMOKE-001-commit-trailer-schema is not implemented yet"
    )
