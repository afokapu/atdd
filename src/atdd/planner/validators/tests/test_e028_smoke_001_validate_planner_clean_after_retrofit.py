# URN: test:govern-lifecycle:smoke-false-green-prevention:E028-SMOKE-001-validate-planner-clean-after-retrofit
# Acceptance: acc:govern-lifecycle:E028-SMOKE-001-validate-planner-clean-after-retrofit
# WMBT: wmbt:govern-lifecycle:E028
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""
SMOKE: atdd validate planner --local --skip-api must exit 0 on the
post-retrofit repo with no planner.smoke.synthetic-fixture-bypass violations.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.smoke, pytest.mark.platform]


def test_validate_planner_clean_after_retrofit():
    """atdd validate planner --local --skip-api exits 0 on the post-retrofit repo."""
    repo_root = find_repo_root()
    result = subprocess.run(
        [sys.executable, "-m", "atdd.cli", "validate", "planner", "--local", "--skip-api"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        "atdd validate planner --local --skip-api exited non-zero — "
        "planner.smoke.synthetic-fixture-bypass violations or other planner failures remain.\n"
        f"stdout:\n{result.stdout[-3000:]}\n"
        f"stderr:\n{result.stderr[-1000:]}"
    )
