# URN: test:project-shared-state:compute-projection-digest:E003-SMOKE-001-projection-digest
# Acceptance: acc:project-shared-state:E003-SMOKE-001-projection-digest
# WMBT: wmbt:project-shared-state:E003
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:E003-SMOKE-001-projection-digest — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:E003-SMOKE-001-projection-digest.

wagon: project-shared-state | feature: compute-projection-digest | phase: SMOKE
WMBT: wmbt:project-shared-state:E003

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_e003_smoke_001_projection_digest(tmp_path) -> None:
    """E003-SMOKE-001-projection-digest — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:E003-SMOKE-001-projection-digest is not implemented yet"
    )
