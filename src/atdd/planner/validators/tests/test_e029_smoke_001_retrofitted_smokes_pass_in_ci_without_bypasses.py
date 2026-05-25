# URN: test:govern-lifecycle:smoke-false-green-prevention:E029-SMOKE-001-retrofitted-smokes-pass-in-ci-without-bypasses
# Acceptance: acc:govern-lifecycle:E029-SMOKE-001-retrofitted-smokes-pass-in-ci-without-bypasses
# WMBT: wmbt:govern-lifecycle:E029
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""
SMOKE: Retrofitted E003-SMOKE tests must pass with no bypass env vars
(no ATDD_RUN_SMOKE, ATDD_SKIP_*, or other overrides).
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.smoke, pytest.mark.platform]

_BYPASS_PREFIXES = ("ATDD_SKIP_", "ATDD_RUN_SMOKE", "ATDD_FORCE_", "ATDD_BYPASS_")


def test_retrofitted_smokes_pass_in_ci_without_bypasses():
    """E003-SMOKE-001 and E003-SMOKE-002 pass with no ATDD bypass env vars."""
    repo_root = find_repo_root()
    test_001 = (
        repo_root
        / "src/atdd/coach/shim/tests/test_e003_smoke_001_correction_loop_end_to_end.py"
    )
    test_002 = (
        repo_root
        / "src/atdd/coach/shim/tests/test_e003_smoke_002_operator_stdout_visible.py"
    )
    for p in (test_001, test_002):
        assert p.exists(), f"Retrofitted test file missing: {p}"

    # Strip all ATDD bypass vars from the subprocess environment.
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if not any(k.startswith(prefix) for prefix in _BYPASS_PREFIXES)
        and k not in ("ATDD_ALL_GATES",)
    }

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_001), str(test_002), "-v", "--tb=short"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=120,
        env=clean_env,
    )
    assert result.returncode == 0, (
        "Retrofitted E003-SMOKE tests failed without bypass env vars — "
        "the retrofit requires bypass flags to pass (false-green risk).\n"
        f"stdout:\n{result.stdout[-4000:]}\n"
        f"stderr:\n{result.stderr[-1000:]}"
    )
