# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E007-SMOKE-001-new-surface-in-pane-no-broken-pipe
# Acceptance: acc:dispatch-ux-defaults-and-primer:E007-SMOKE-001-new-surface-in-pane-no-broken-pipe
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E007
# Phase: SMOKE
# Layer: integration
# Runtime: python
"""E007-SMOKE-001 — CmuxBackend.new_surface_in_pane succeeds in a real cmux session.

SMOKE: requires ATDD_RUN_SMOKE=1 and a real cmux session (CMUX_WORKSPACE_ID set).
Verified: resolve_focused_pane() returns a pane ref; new_surface_in_pane()
invokes cmux new-surface --pane <ref> (canonical RPC) without Broken pipe.
"""
from __future__ import annotations

import os
import re
import shutil

import pytest

pytestmark = [pytest.mark.platform]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_new_surface_in_pane_no_broken_pipe():
    """CmuxBackend.resolve_focused_pane + new_surface_in_pane work in real cmux session."""
    if not os.environ.get("CMUX_WORKSPACE_ID"):
        pytest.skip("SMOKE requires CMUX_WORKSPACE_ID (must run inside a cmux session)")
    if not shutil.which("cmux"):
        pytest.skip("cmux not installed")

    from atdd.coach.utils.multiplexer import CmuxBackend

    backend = CmuxBackend()

    pane_ref = backend.resolve_focused_pane()
    assert re.match(r"^pane:\d+$", pane_ref), (
        f"resolve_focused_pane() must return 'pane:N'; got {pane_ref!r}"
    )

    surface_ref = backend.new_surface_in_pane(
        pane_ref=pane_ref,
        cwd=os.getcwd(),
        command="true",
        name="atdd-e007-smoke-probe",
    )
    assert surface_ref, (
        f"new_surface_in_pane() returned empty ref (expected 'surface:N')"
    )
    assert "broken pipe" not in str(surface_ref).lower(), (
        f"new_surface_in_pane() result looks like an error: {surface_ref!r}"
    )
