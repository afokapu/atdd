# URN: test:migrate-projection-authority:compare-shadow-projection:M001-SMOKE-001-shadow-projection-report
# Acceptance: acc:migrate-projection-authority:M001-SMOKE-001-shadow-projection-report
# WMBT: wmbt:migrate-projection-authority:M001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:M001-SMOKE-001-shadow-projection-report — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:M001-SMOKE-001-shadow-projection-report.

wagon: migrate-projection-authority | feature: compare-shadow-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:M001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_m001_smoke_001_shadow_projection_report(tmp_path) -> None:
    """M001-SMOKE-001-shadow-projection-report — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:M001-SMOKE-001-shadow-projection-report is not implemented yet"
    )
