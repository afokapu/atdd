# URN: test:enforce-merge-authority:parse-commit-trailer:E001-UNIT-001-parser-drops-malformed-trailers
# Acceptance: acc:enforce-merge-authority:E001-UNIT-001-parser-drops-malformed-trailers
# WMBT: wmbt:enforce-merge-authority:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:E001-UNIT-001-parser-drops-malformed-trailers — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:E001-UNIT-001-parser-drops-malformed-trailers.

wagon: enforce-merge-authority | feature: parse-commit-trailer | phase: RED
WMBT: wmbt:enforce-merge-authority:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (the parser refuses a schema-violating trailer block instead of silently dropping it). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_e001_unit_001_parser_drops_malformed_trailers() -> None:
    """E001-UNIT-001-parser-drops-malformed-trailers — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:E001-UNIT-001-parser-drops-malformed-trailers is not implemented yet"
    )
