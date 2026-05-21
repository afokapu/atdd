# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-worktree-lifecycle:E004-SMOKE-001-worktree-reused-not-duplicated
# Acceptance: acc:dispatch-ux-defaults-and-primer:E004-SMOKE-001-worktree-reused-not-duplicated
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E004
# Phase: SMOKE
# Layer: integration
# Runtime: python
"""E004-SMOKE-001 — atdd coach reuses an existing worktree without 'already exists' git error.

SMOKE: requires ATDD_RUN_SMOKE=1 and a pre-existing issue worktree on disk.
"""
from __future__ import annotations

import os
import pytest

pytestmark = [pytest.mark.platform]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_worktree_reused_not_duplicated():
    """atdd coach reuses an existing worktree and logs 'Reusing existing worktree'."""
    pytest.fail(
        "E004-SMOKE-001 not yet implemented — "
        "GREEN code needed before SMOKE verification"
    )
