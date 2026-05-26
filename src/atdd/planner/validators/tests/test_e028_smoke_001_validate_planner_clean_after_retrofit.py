# URN: test:govern-lifecycle:smoke-false-green-prevention:E028-SMOKE-001-validate-planner-clean-after-retrofit
# Acceptance: acc:govern-lifecycle:E028-SMOKE-001-validate-planner-clean-after-retrofit
# WMBT: wmbt:govern-lifecycle:E028
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""
SMOKE: The synthetic-fixture-bypass planner validator must run cleanly and report
zero violations on the post-retrofit repo.  Invokes the validator test file directly
via pytest (not the full atdd validate planner suite) to keep runtime under 30s.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import atdd
import pytest

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.smoke, pytest.mark.platform]

_VALIDATOR_FILE = (
    Path(atdd.__file__).parent
    / "planner"
    / "validators"
    / "test_smoke_synthetic_fixture_bypass.py"
)


def test_validate_planner_clean_after_retrofit():
    """Synthetic-fixture-bypass validator exits 0 — zero violations on the post-retrofit repo."""
    repo_root = find_repo_root()
    assert _VALIDATOR_FILE.exists(), (
        f"Validator file not found at {_VALIDATOR_FILE} — "
        "test_smoke_synthetic_fixture_bypass.py must be installed with the atdd package."
    )
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            str(_VALIDATOR_FILE),
            "-v", "--tb=short", "-q",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        "synthetic-fixture-bypass planner validator reported violations on the post-retrofit repo.\n"
        f"stdout:\n{result.stdout[-3000:]}\n"
        f"stderr:\n{result.stderr[-500:]}"
    )
