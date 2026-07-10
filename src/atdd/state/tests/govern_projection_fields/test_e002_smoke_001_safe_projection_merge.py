# URN: test:govern-projection-fields:merge-projection-objects:E002-SMOKE-001-safe-projection-merge
# Acceptance: acc:govern-projection-fields:E002-SMOKE-001-safe-projection-merge
# WMBT: wmbt:govern-projection-fields:E002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:E002-SMOKE-001-safe-projection-merge — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:E002-SMOKE-001-safe-projection-merge.

wagon: govern-projection-fields | feature: merge-projection-objects | phase: SMOKE
WMBT: wmbt:govern-projection-fields:E002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_e002_smoke_001_safe_projection_merge(tmp_path) -> None:
    """E002-SMOKE-001-safe-projection-merge — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:E002-SMOKE-001-safe-projection-merge is not implemented yet"
    )
