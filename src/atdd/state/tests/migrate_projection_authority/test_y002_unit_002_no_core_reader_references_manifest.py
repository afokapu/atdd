# URN: test:migrate-projection-authority:decommission-manifest-fallback:Y002-UNIT-002-no-core-reader-references-manifest
# Acceptance: acc:migrate-projection-authority:Y002-UNIT-002-no-core-reader-references-manifest
# WMBT: wmbt:migrate-projection-authority:Y002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:Y002-UNIT-002-no-core-reader-references-manifest — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:Y002-UNIT-002-no-core-reader-references-manifest.

wagon: migrate-projection-authority | feature: decommission-manifest-fallback | phase: RED
WMBT: wmbt:migrate-projection-authority:Y002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_y002_unit_002_no_core_reader_references_manifest(tmp_path) -> None:
    """Y002-UNIT-002-no-core-reader-references-manifest — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:Y002-UNIT-002-no-core-reader-references-manifest is not implemented yet"
    )
