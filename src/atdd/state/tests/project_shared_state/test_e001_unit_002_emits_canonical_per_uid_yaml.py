# URN: test:project-shared-state:project-store:E001-UNIT-002-emits-canonical-per-uid-yaml
# Acceptance: acc:project-shared-state:E001-UNIT-002-emits-canonical-per-uid-yaml
# WMBT: wmbt:project-shared-state:E001
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:E001-UNIT-002-emits-canonical-per-uid-yaml — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:E001-UNIT-002-emits-canonical-per-uid-yaml.

wagon: project-shared-state | feature: project-store | phase: GREEN
WMBT: wmbt:project-shared-state:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_e001_unit_002_emits_canonical_per_uid_yaml(tmp_path) -> None:
    """E001-UNIT-002-emits-canonical-per-uid-yaml — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:E001-UNIT-002-emits-canonical-per-uid-yaml is not implemented yet"
    )
