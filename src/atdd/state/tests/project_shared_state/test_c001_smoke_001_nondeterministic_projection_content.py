# URN: test:project-shared-state:project-store:C001-SMOKE-001-nondeterministic-projection-content
# Acceptance: acc:project-shared-state:C001-SMOKE-001-nondeterministic-projection-content
# WMBT: wmbt:project-shared-state:C001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:C001-SMOKE-001-nondeterministic-projection-content — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:C001-SMOKE-001-nondeterministic-projection-content.

wagon: project-shared-state | feature: project-store | phase: SMOKE
WMBT: wmbt:project-shared-state:C001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_c001_smoke_001_nondeterministic_projection_content(tmp_path) -> None:
    """C001-SMOKE-001-nondeterministic-projection-content — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:C001-SMOKE-001-nondeterministic-projection-content is not implemented yet"
    )
