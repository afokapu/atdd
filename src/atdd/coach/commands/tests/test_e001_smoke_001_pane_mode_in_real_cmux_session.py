# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E001-SMOKE-001-pane-mode-in-real-cmux-session
# Acceptance: acc:dispatch-ux-defaults-and-primer:E001-SMOKE-001-pane-mode-in-real-cmux-session
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
"""E001-SMOKE-001 — atdd coach resolves 'surface' mode against a real cmux session.

SMOKE: requires ATDD_RUN_SMOKE=1 and a real cmux session (CMUX_WORKSPACE_ID set).
Verified: resolve_multiplexer_mode returns 'surface' using the live env.
"""
from __future__ import annotations

import os
import shutil

import pytest

pytestmark = [pytest.mark.platform]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_surface_mode_in_real_cmux_session():
    """resolve_multiplexer_mode returns 'surface' inside a real cmux session."""
    if not os.environ.get("CMUX_WORKSPACE_ID"):
        pytest.skip("SMOKE requires CMUX_WORKSPACE_ID (must run inside a cmux session)")
    if not shutil.which("cmux"):
        pytest.skip("cmux not installed")

    from atdd.coach.commands.coach import resolve_multiplexer_mode

    result = resolve_multiplexer_mode(explicit_flag=None, env=dict(os.environ))
    assert result == "surface", (
        f"Inside real cmux session (CMUX_WORKSPACE_ID={os.environ['CMUX_WORKSPACE_ID']!r}), "
        f"resolve_multiplexer_mode must return 'surface' (E007); got {result!r}"
    )
