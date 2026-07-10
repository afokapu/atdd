# URN: test:project-shared-state:hydrate-projection:E002-SMOKE-001-projection-hydration
# Acceptance: acc:project-shared-state:E002-SMOKE-001-projection-hydration
# WMBT: wmbt:project-shared-state:E002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:E002-SMOKE-001-projection-hydration — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:E002-SMOKE-001-projection-hydration.

wagon: project-shared-state | feature: hydrate-projection | phase: SMOKE
WMBT: wmbt:project-shared-state:E002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_e002_smoke_001_projection_hydration(tmp_path) -> None:
    """E002-SMOKE-001-projection-hydration — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:E002-SMOKE-001-projection-hydration is not implemented yet"
    )
