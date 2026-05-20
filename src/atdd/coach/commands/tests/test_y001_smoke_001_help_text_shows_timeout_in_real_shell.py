# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:Y001-SMOKE-001-help-text-shows-timeout-in-real-shell
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y001-SMOKE-001-help-text-shows-timeout-in-real-shell
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y001
# Phase: SMOKE
# Layer: integration
# Runtime: python
"""Y001-SMOKE-001 — atdd coach --help in a real shell shows ATDD_WORKER_READY_TIMEOUT and 30.

SMOKE: requires ATDD_RUN_SMOKE=1 and atdd installed in the shell.
"""
from __future__ import annotations

import os
import subprocess
import sys
import pytest

pytestmark = [pytest.mark.platform]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_help_text_shows_timeout_in_real_shell():
    """atdd coach --help output in real shell mentions ATDD_WORKER_READY_TIMEOUT and '30'."""
    result = subprocess.run(
        ["atdd", "coach", "--help"],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    assert "ATDD_WORKER_READY_TIMEOUT" in output, (
        f"'atdd coach --help' must mention ATDD_WORKER_READY_TIMEOUT; "
        f"got: {output!r}"
    )
    assert "30" in output, (
        f"'atdd coach --help' must show default '30'; got: {output!r}"
    )
