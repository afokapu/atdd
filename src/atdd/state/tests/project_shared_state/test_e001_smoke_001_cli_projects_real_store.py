# URN: test:project-shared-state:project-store:E001-SMOKE-001-cli-projects-real-store
# Acceptance: acc:project-shared-state:E001-SMOKE-001-cli-projects-real-store
# WMBT: wmbt:project-shared-state:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:E001-SMOKE-001-cli-projects-real-store — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:E001-SMOKE-001-cli-projects-real-store.

wagon: project-shared-state | feature: project-store | phase: SMOKE
WMBT: wmbt:project-shared-state:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_e001_smoke_001_cli_projects_real_store(tmp_path) -> None:
    """E001-SMOKE-001-cli-projects-real-store — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:E001-SMOKE-001-cli-projects-real-store is not implemented yet"
    )
