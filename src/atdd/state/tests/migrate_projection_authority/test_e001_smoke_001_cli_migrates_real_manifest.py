# URN: test:migrate-projection-authority:migrate-manifest-projection:E001-SMOKE-001-cli-migrates-real-manifest
# Acceptance: acc:migrate-projection-authority:E001-SMOKE-001-cli-migrates-real-manifest
# WMBT: wmbt:migrate-projection-authority:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:E001-SMOKE-001-cli-migrates-real-manifest — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:E001-SMOKE-001-cli-migrates-real-manifest.

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_e001_smoke_001_cli_migrates_real_manifest(tmp_path) -> None:
    """E001-SMOKE-001-cli-migrates-real-manifest — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:E001-SMOKE-001-cli-migrates-real-manifest is not implemented yet"
    )
