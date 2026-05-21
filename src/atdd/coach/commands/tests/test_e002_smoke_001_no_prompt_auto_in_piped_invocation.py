# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E002-SMOKE-001-no-prompt-auto-in-piped-invocation
# Acceptance: acc:dispatch-ux-defaults-and-primer:E002-SMOKE-001-no-prompt-auto-in-piped-invocation
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E002
# Phase: SMOKE
# Layer: integration
# Runtime: python
"""E002-SMOKE-001 — atdd coach piped with stdin not a TTY does not block on persona prompt.

SMOKE: requires ATDD_RUN_SMOKE=1 and a real shell environment.
"""
from __future__ import annotations

import os
import pytest

pytestmark = [pytest.mark.platform]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_no_prompt_auto_in_piped_invocation():
    """atdd coach piped (stdin not a TTY) does not block on persona prompt."""
    pytest.fail(
        "E002-SMOKE-001 not yet implemented — "
        "GREEN code needed before SMOKE verification"
    )
