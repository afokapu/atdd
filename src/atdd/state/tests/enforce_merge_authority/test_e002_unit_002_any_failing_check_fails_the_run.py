# URN: test:enforce-merge-authority:run-merge-checks:E002-UNIT-002-any-failing-check-fails-the-run
# Acceptance: acc:enforce-merge-authority:E002-UNIT-002-any-failing-check-fails-the-run
# WMBT: wmbt:enforce-merge-authority:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:E002-UNIT-002-any-failing-check-fails-the-run — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:E002-UNIT-002-any-failing-check-fails-the-run.

wagon: enforce-merge-authority | feature: run-merge-checks | phase: RED
WMBT: wmbt:enforce-merge-authority:E002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (the merge-authority run fails when any one of the full required-check set fails). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_e002_unit_002_any_failing_check_fails_the_run() -> None:
    """E002-UNIT-002-any-failing-check-fails-the-run — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:E002-UNIT-002-any-failing-check-fails-the-run is not implemented yet"
    )
