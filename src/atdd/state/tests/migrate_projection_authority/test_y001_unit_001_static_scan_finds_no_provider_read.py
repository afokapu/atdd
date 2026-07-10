# URN: test:migrate-projection-authority:remove-github-reads:Y001-UNIT-001-static-scan-finds-no-provider-read
# Acceptance: acc:migrate-projection-authority:Y001-UNIT-001-static-scan-finds-no-provider-read
# WMBT: wmbt:migrate-projection-authority:Y001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:Y001-UNIT-001-static-scan-finds-no-provider-read — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:Y001-UNIT-001-static-scan-finds-no-provider-read.

wagon: migrate-projection-authority | feature: remove-github-reads | phase: RED
WMBT: wmbt:migrate-projection-authority:Y001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_y001_unit_001_static_scan_finds_no_provider_read(tmp_path) -> None:
    """Y001-UNIT-001-static-scan-finds-no-provider-read — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:Y001-UNIT-001-static-scan-finds-no-provider-read is not implemented yet"
    )
