# URN: test:govern-lifecycle:systemic-registry-drift-enforcement:E021-INTEGRATION-001-ci-check-fails-on-drifted-pr
# Acceptance: acc:govern-lifecycle:E021-INTEGRATION-001-ci-check-fails-on-drifted-pr
# WMBT: wmbt:govern-lifecycle:E021
# Phase: SMOKE
# Layer: backend.integration
"""
AC-INTEGRATION-001: A PR that adds a new WMBT entry to a source wagon file without
re-syncing the mirror fails the atdd-registry-drift CI job.

Given:
  - atdd CLI installed from local source (PYTHONPATH=src)
  - A temporary git repo with a plan/<wagon>/_<wagon>.yaml that has an extra WMBT entry
  - plan/_wagons.yaml has NOT been updated to reflect the new WMBT count

When:
  - 'atdd registry update --check' is invoked against the temporary repo

Then:
  - Exit code is non-zero
  - Output names the drifted wagon/field (e.g. 'wmbt.total mismatch')
  - Output contains the fix-hint string 'atdd registry update --yes'

RED state: The current check output prints 'Drift detected in wagon registry' but does
NOT include 'atdd registry update --yes' in the output. This test fails on the
fix-hint assertion until the check output is updated to include the remediation hint.
"""
from __future__ import annotations

import os
import subprocess
import sys
import yaml
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[6]


@pytest.fixture()
def drifted_repo(tmp_path):
    """Repo where a wagon source has an extra WMBT entry but _wagons.yaml is stale."""
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    wagon_dir = plan_dir / "my_wagon"
    wagon_dir.mkdir()

    # Source manifest: claims 3 WMBTs
    manifest = {
        "wagon": "my-wagon",
        "description": "My wagon",
        "theme": "commons",
        "subject": "agent:coder",
        "context": "in-lifecycle",
        "action": "acts",
        "goal": "achieves",
        "outcome": "achieved",
        "wmbt": {"total": 3},
    }
    with open(wagon_dir / "_my_wagon.yaml", "w") as f:
        yaml.dump(manifest, f)

    # Mirror: still says 2 WMBTs — DRIFT
    wagons_data = {
        "wagons": [
            {
                "wagon": "my-wagon",
                "description": "My wagon",
                "theme": "commons",
                "wmbt": {"total": 2},
            }
        ]
    }
    with open(plan_dir / "_wagons.yaml", "w") as f:
        yaml.dump(wagons_data, f)

    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    with open(contracts_dir / "_artifacts.yaml", "w") as f:
        yaml.dump({"artifacts": []}, f)

    with open(plan_dir / "_trains.yaml", "w") as f:
        yaml.dump({"trains": []}, f)

    return tmp_path


def _run_registry_check(repo_dir: Path) -> subprocess.CompletedProcess:
    """Invoke atdd registry update --check via the installed atdd binary."""
    env = os.environ.copy()
    src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        ["atdd", "registry", "update", "--check"],
        capture_output=True,
        text=True,
        cwd=str(repo_dir),
        env=env,
    )


def test_registry_check_exits_nonzero_on_drifted_repo(drifted_repo):
    """atdd registry update --check exits non-zero when wagon mirror is out of sync."""
    result = _run_registry_check(drifted_repo)
    assert result.returncode != 0, (
        f"Expected non-zero exit when drift is detected, got 0.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_registry_check_output_names_drifted_wagon(drifted_repo):
    """atdd registry update --check output must name the drifted wagon."""
    result = _run_registry_check(drifted_repo)
    output = result.stdout + result.stderr
    assert "my-wagon" in output or "my_wagon" in output or "wagon" in output.lower(), (
        f"Expected drifted wagon name in output.\nOutput:\n{output}"
    )


def test_registry_check_output_contains_fix_hint(drifted_repo):
    """atdd registry update --check output must include 'atdd registry update --yes' fix-hint.

    RED: Current output says 'Drift detected' but NOT 'atdd registry update --yes'.
    This assertion fails until the fix-hint is added to the check output.
    """
    result = _run_registry_check(drifted_repo)
    output = result.stdout + result.stderr
    assert "atdd registry update --yes" in output, (
        "Expected fix-hint 'atdd registry update --yes' in check output.\n"
        "Current output only says 'Drift detected' — add the remediation hint.\n"
        f"Actual output:\n{output}"
    )
