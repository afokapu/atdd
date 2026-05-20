# URN: test:dispatch-ux-defaults-and-primer:multiplexer-primer:E005-SMOKE-001-primer-printed-in-real-cmux-session
# Acceptance: acc:dispatch-ux-defaults-and-primer:E005-SMOKE-001-primer-printed-in-real-cmux-session
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E005
# Phase: SMOKE
# Layer: integration
# Runtime: python
"""E005-SMOKE-001 — atdd coach prints the cmux primer on first dispatch, not on second.

SMOKE: requires ATDD_RUN_SMOKE=1 and a real cmux session (CMUX_WORKSPACE_ID set).
"""
from __future__ import annotations

import os
import pytest

pytestmark = [pytest.mark.platform]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_primer_printed_in_real_cmux_session():
    """First dispatch prints 'cmux tree' primer; second dispatch does not reprint."""
    if not os.environ.get("CMUX_WORKSPACE_ID"):
        pytest.skip("SMOKE requires CMUX_WORKSPACE_ID")
    pytest.fail(
        "E005-SMOKE-001 not yet implemented — "
        "GREEN code needed before SMOKE verification"
    )
