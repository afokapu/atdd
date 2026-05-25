# URN: test:govern-lifecycle:smoke-false-green-prevention:E029-INTEGRATION-001-retrofitted-smoke-tests-pass
# Acceptance: acc:govern-lifecycle:E029-INTEGRATION-001-retrofitted-smoke-tests-pass
# WMBT: wmbt:govern-lifecycle:E029
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""
GREEN: Both retrofitted E003-SMOKE tests must execute and pass using real
atdd spawn wiring without ATDD_RUN_SMOKE set.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.planner]


def test_retrofitted_smoke_tests_pass():
    """Both E003-SMOKE tests must pass with real spawn wiring — no ATDD_RUN_SMOKE bypass."""
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

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_001), str(test_002), "-v", "--tb=short"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "Retrofitted E003-SMOKE tests failed — real spawn wiring is broken.\n"
        f"stdout:\n{result.stdout[-4000:]}\n"
        f"stderr:\n{result.stderr[-1000:]}"
    )
