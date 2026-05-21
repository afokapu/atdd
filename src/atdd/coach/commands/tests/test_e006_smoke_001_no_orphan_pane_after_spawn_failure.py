# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-worktree-lifecycle:E006-SMOKE-001-no-orphan-pane-after-spawn-failure
# Acceptance: acc:dispatch-ux-defaults-and-primer:E006-SMOKE-001-no-orphan-pane-after-spawn-failure
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E006
# Phase: SMOKE
# Layer: integration
# Runtime: python
"""E006-SMOKE-001 — no orphan surface remains after a forced spawn failure in real cmux.

SMOKE: requires ATDD_RUN_SMOKE=1, CMUX_WORKSPACE_ID set, and ATDD_WORKER_READY_TIMEOUT=1.
"""
from __future__ import annotations

import os
import pytest

pytestmark = [pytest.mark.platform]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_no_orphan_pane_after_spawn_failure():
    """Surface count in workspace:1 unchanged after forced WorkerReadinessTimeout."""
    if not os.environ.get("CMUX_WORKSPACE_ID"):
        pytest.skip("SMOKE requires CMUX_WORKSPACE_ID")
    pytest.fail(
        "E006-SMOKE-001 not yet implemented — "
        "GREEN code needed before SMOKE verification"
    )
