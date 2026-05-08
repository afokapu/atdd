# URN: test:train:0002-coach-drives-lifecycle:E2E-002-plan-artifacts-smoke
# Train: train:0002-coach-drives-lifecycle
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: SMOKE for the validation slice — invoke `atdd validate planner --quick`
#          as a real subprocess against the live worktree and assert the new
#          wagon's WMBT YAMLs do not introduce planner-vocabulary violations.
"""
Smoke test for train:0002-coach-drives-lifecycle.

Runs the actual atdd CLI as a subprocess and confirms that the planner
vocabulary validators (dimensions, lenses, statement-construction) accept
the new freeze-runtime-contracts wagon's WMBT YAMLs without complaint.

The validation slice is documentation-and-schemas-only; the real coach v9
end-to-end smoke (driving an issue from atdd coach <N> through COMPLETE)
arrives via Track Q1 once the implementation lands.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root


REPO_ROOT = find_repo_root()


@pytest.fixture(scope="module")
def atdd_binary():
    binary = shutil.which("atdd")
    if not binary:
        pytest.skip("atdd binary not on PATH (smoke needs the real CLI)")
    return binary


def _run_validator(binary: str, validator_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(validator_path),
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_planner_vocabulary_accepts_new_wagon_wmbts(atdd_binary):
    """The wmbt-vocabulary planner validators accept all four new WMBTs.

    A failure here would mean the freeze-runtime-contracts WMBTs use an
    unauthorized dimension, lens, or statement shape — directly tied to
    plan/freeze_runtime_contracts/D00[1-4].yaml.
    """
    import atdd.planner.validators.test_wmbt_vocabulary as mod

    validator_path = Path(mod.__file__)
    result = _run_validator(atdd_binary, validator_path)

    combined = (result.stdout or "") + (result.stderr or "")
    assert "freeze_runtime_contracts" not in combined or "passed" in combined.lower(), (
        f"wmbt-vocabulary flagged the new wagon's WMBTs:\n{combined}"
    )

    expected_files = {
        REPO_ROOT / "plan" / "freeze_runtime_contracts" / f"{step}.yaml"
        for step in ("D001", "D002", "D003", "D004")
    }
    for fp in expected_files:
        assert fp.exists(), f"WMBT YAML missing on disk: {fp}"


def test_train_yaml_consumed_by_atdd_inventory(atdd_binary):
    """`atdd inventory` must enumerate the new train without crashing.

    Tests the train-registration path end-to-end: plan/_trains.yaml entry +
    plan/_trains/0002-coach-drives-lifecycle.yaml file are both readable by
    the live CLI.
    """
    result = subprocess.run(
        [atdd_binary, "inventory"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )

    combined = (result.stdout or "") + (result.stderr or "")
    assert "0002-coach-drives-lifecycle" in combined, (
        f"`atdd inventory` did not surface the new train:\n{combined[:2000]}"
    )
