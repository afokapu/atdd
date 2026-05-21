# URN: test:dispatch-ux-defaults-and-primer:multiplexer-primer:Y003-SMOKE-001-resume-absent-from-real-help-output
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y003-SMOKE-001-resume-absent-from-real-help-output
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y003
# Phase: SMOKE
# Layer: integration
# Runtime: python
"""Y003-SMOKE-001 — atdd coach --help in real shell does not show --resume.

SMOKE: requires ATDD_RUN_SMOKE=1 and atdd installed in the shell.
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
def test_resume_absent_from_real_help_output():
    """atdd coach --help in real shell does not list --resume as a visible option."""
    result = subprocess.run(
        ["atdd", "coach", "--help"],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    assert "--resume" not in output, (
        f"'atdd coach --help' must NOT show --resume until J6 lands; "
        f"got: {output!r}"
    )
    assert "Recovery" in output or "re-run" in output.lower(), (
        f"'atdd coach --help' must contain a recovery note; got: {output!r}"
    )
