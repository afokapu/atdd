# URN: test:enforce-merge-authority:run-merge-checks:E002-SMOKE-001-illegal-projection-rejected-end-end
# Acceptance: acc:enforce-merge-authority:E002-SMOKE-001-illegal-projection-rejected-end-end
# WMBT: wmbt:enforce-merge-authority:E002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:E002-SMOKE-001-illegal-projection-rejected-end-end — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:E002-SMOKE-001-illegal-projection-rejected-end-end.

wagon: enforce-merge-authority | feature: run-merge-checks | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:E002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (an illegal projection is rejected end-to-end by the merge-authority run against real infrastructure). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_e002_smoke_001_illegal_projection_rejected_end_end(tmp_path) -> None:
    """E002-SMOKE-001-illegal-projection-rejected-end-end — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:E002-SMOKE-001-illegal-projection-rejected-end-end is not implemented yet"
    )
