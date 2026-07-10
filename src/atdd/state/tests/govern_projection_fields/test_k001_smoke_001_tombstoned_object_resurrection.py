# URN: test:govern-projection-fields:mark-object-tombstone:K001-SMOKE-001-tombstoned-object-resurrection
# Acceptance: acc:govern-projection-fields:K001-SMOKE-001-tombstoned-object-resurrection
# WMBT: wmbt:govern-projection-fields:K001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:K001-SMOKE-001-tombstoned-object-resurrection — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:K001-SMOKE-001-tombstoned-object-resurrection.

wagon: govern-projection-fields | feature: mark-object-tombstone | phase: SMOKE
WMBT: wmbt:govern-projection-fields:K001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_k001_smoke_001_tombstoned_object_resurrection(tmp_path) -> None:
    """K001-SMOKE-001-tombstoned-object-resurrection — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:K001-SMOKE-001-tombstoned-object-resurrection is not implemented yet"
    )
