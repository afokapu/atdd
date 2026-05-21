# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:Y002-SMOKE-001-banner-absent-after-sync-in-real-env
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y002-SMOKE-001-banner-absent-after-sync-in-real-env
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y002
# Phase: SMOKE
# Layer: integration
# Runtime: python
"""Y002-SMOKE-001 — atdd invocations after atdd sync do not print the upgrade banner.

SMOKE: requires ATDD_RUN_SMOKE=1 and atdd sync to have been run in the real env.
"""
from __future__ import annotations

import os
import subprocess
import pytest

pytestmark = [pytest.mark.platform]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_banner_absent_after_sync_in_real_env():
    """After atdd sync, atdd status does not print the upgrade warning banner."""
    result = subprocess.run(
        ["atdd", "status"],
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert "ATDD upgraded" not in combined, (
        f"Upgrade banner must not appear after atdd sync; got: {combined!r}"
    )
