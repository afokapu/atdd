# URN: test:project-shared-state:verify-projection-canonicality:C002-SMOKE-001-ci-job-blocks-noncanonical-push
# Acceptance: acc:project-shared-state:C002-SMOKE-001-ci-job-blocks-noncanonical-push
# WMBT: wmbt:project-shared-state:C002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:project-shared-state:C002-SMOKE-001-ci-job-blocks-noncanonical-push — fails until the project-shared-state wagon implements it (train 0006). Refs #1433.
"""RED skeleton for acc:project-shared-state:C002-SMOKE-001-ci-job-blocks-noncanonical-push.

wagon: project-shared-state | feature: verify-projection-canonicality | phase: SMOKE
WMBT: wmbt:project-shared-state:C002

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the project-shared-state wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="project-shared-state not yet implemented (RED; #1433)")
def test_c002_smoke_001_ci_job_blocks_noncanonical_push(tmp_path) -> None:
    """C002-SMOKE-001-ci-job-blocks-noncanonical-push — behaviour not yet implemented."""
    raise AssertionError(
        "RED: project-shared-state acceptance acc:project-shared-state:C002-SMOKE-001-ci-job-blocks-noncanonical-push is not implemented yet"
    )
