# URN: test:govern-projection-fields:merge-projection-objects:R001-SMOKE-001-unsafe-merge-conflict
# Acceptance: acc:govern-projection-fields:R001-SMOKE-001-unsafe-merge-conflict
# WMBT: wmbt:govern-projection-fields:R001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:R001-SMOKE-001-unsafe-merge-conflict — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:R001-SMOKE-001-unsafe-merge-conflict.

wagon: govern-projection-fields | feature: merge-projection-objects | phase: SMOKE
WMBT: wmbt:govern-projection-fields:R001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_r001_smoke_001_unsafe_merge_conflict(tmp_path) -> None:
    """R001-SMOKE-001-unsafe-merge-conflict — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:R001-SMOKE-001-unsafe-merge-conflict is not implemented yet"
    )
