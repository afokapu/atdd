# URN: test:migrate-projection-authority:decommission-manifest-fallback:Y002-SMOKE-001-manifest-read-fallback
# Acceptance: acc:migrate-projection-authority:Y002-SMOKE-001-manifest-read-fallback
# WMBT: wmbt:migrate-projection-authority:Y002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:migrate-projection-authority:Y002-SMOKE-001-manifest-read-fallback — fails until the migrate-projection-authority wagon implements it (train 0006). Refs #1400.
"""RED skeleton for acc:migrate-projection-authority:Y002-SMOKE-001-manifest-read-fallback.

wagon: migrate-projection-authority | feature: decommission-manifest-fallback | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:Y002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the migrate-projection-authority wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="migrate-projection-authority not yet implemented (RED; #1400)")
def test_y002_smoke_001_manifest_read_fallback(tmp_path) -> None:
    """Y002-SMOKE-001-manifest-read-fallback — behaviour not yet implemented."""
    raise AssertionError(
        "RED: migrate-projection-authority acceptance acc:migrate-projection-authority:Y002-SMOKE-001-manifest-read-fallback is not implemented yet"
    )
