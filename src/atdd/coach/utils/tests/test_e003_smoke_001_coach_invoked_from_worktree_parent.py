# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-worktree-lifecycle:E003-SMOKE-001-coach-invoked-from-worktree-parent
# Acceptance: acc:dispatch-ux-defaults-and-primer:E003-SMOKE-001-coach-invoked-from-worktree-parent
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E003
# Phase: SMOKE
# Layer: integration
# Runtime: python
"""E003-SMOKE-001 — atdd coach invoked from the worktree-parent auto-detects the worktree.

SMOKE: requires ATDD_RUN_SMOKE=1 and a real worktree layout (project-parent/feat-slug/).
"""
from __future__ import annotations

import os
import pytest

pytestmark = [pytest.mark.platform]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_coach_invoked_from_worktree_parent():
    """atdd coach from the worktree-parent does not crash with 'not a git repository'."""
    pytest.fail(
        "E003-SMOKE-001 not yet implemented — "
        "GREEN code needed before SMOKE verification"
    )
