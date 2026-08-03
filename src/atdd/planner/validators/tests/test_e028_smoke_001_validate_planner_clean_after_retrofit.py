# URN: test:govern-lifecycle:smoke-false-green-prevention:E028-SMOKE-001-validate-planner-clean-after-retrofit
# Acceptance: acc:govern-lifecycle:E028-SMOKE-001-validate-planner-clean-after-retrofit
# WMBT: wmbt:govern-lifecycle:E028
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""
SMOKE: The synthetic-fixture-bypass validator must run cleanly and report zero
violations on the post-retrofit repo.  Invokes the convention variant's clean-baseline
node directly via pytest (not the full atdd validate planner suite) to keep runtime
under 30s.  Retargeted off the retired legacy planner validator in #1385.
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
    / "validators"
    / "conventions"
    / "policy"
    / "test_smoke_synthetic_fixture_bypass.py"
)
# Pin the clean-baseline node explicitly: running the whole file would also pass on the
# variant's contract test alone, which asserts nothing about the repo (#1385).
_CLEAN_BASELINE_NODE = "test_clean_baseline_zero_on_real_graph"


def test_validate_planner_clean_after_retrofit():
    """Synthetic-fixture-bypass validator exits 0 — zero violations on the post-retrofit repo."""
    repo_root = find_repo_root()
    assert _VALIDATOR_FILE.exists(), (
        f"Validator file not found at {_VALIDATOR_FILE} — "
        "conventions/policy/test_smoke_synthetic_fixture_bypass.py must be installed "
        "with the atdd package."
    )
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            f"{_VALIDATOR_FILE}::{_CLEAN_BASELINE_NODE}",
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
