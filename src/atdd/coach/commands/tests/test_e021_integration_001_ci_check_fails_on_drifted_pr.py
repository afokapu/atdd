# URN: test:govern-lifecycle:systemic-registry-drift-enforcement:E021-INTEGRATION-001-ci-check-fails-on-drifted-pr
# Acceptance: acc:govern-lifecycle:E021-INTEGRATION-001-ci-check-fails-on-drifted-pr
# WMBT: wmbt:govern-lifecycle:E021
# Phase: SMOKE
# Layer: backend.integration
"""
AC-INTEGRATION-001: A PR that adds a new WMBT entry to a source wagon file without
re-syncing the mirror fails the atdd-registry-drift CI job.

Given:
  - atdd CLI invoked via the local RegistryBuilder (PYTHONPATH=src in CI)
  - A temporary repo with plan/<wagon>/_<wagon>.yaml that has an extra WMBT entry
  - plan/_wagons.yaml has NOT been updated to reflect the new WMBT count

When:
  - RegistryBuilder.check() is called against the drifted temporary repo
  - OR update_registries(check=True) is called via ATDDCoach

Then:
  - Return code is non-zero (has_changes is True)
  - The check output names the drifted wagon
  - The check output contains the fix-hint 'atdd registry update --yes'
"""
from __future__ import annotations

import yaml
from pathlib import Path
from io import StringIO
from contextlib import redirect_stdout

import pytest

from atdd.coach.commands.registry import RegistryBuilder


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


def test_registry_check_exits_nonzero_on_drifted_repo(drifted_repo):
    """RegistryBuilder.check() returns non-zero when wagon mirror is out of sync."""
    builder = RegistryBuilder(drifted_repo)
    exit_code = builder.check()
    assert exit_code != 0, (
        f"Expected non-zero exit when drift is detected, got {exit_code}."
    )


def test_registry_check_output_names_drifted_wagon(drifted_repo, capsys):
    """RegistryBuilder check output must name the drifted wagon."""
    builder = RegistryBuilder(drifted_repo)
    builder.check()
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "my-wagon" in output or "my_wagon" in output or "UPDATED WAGONS" in output, (
        f"Expected drifted wagon name in check output.\nOutput:\n{output}"
    )


def test_registry_check_output_contains_fix_hint(drifted_repo, capsys):
    """RegistryBuilder check output must include 'atdd registry update --yes' fix-hint."""
    builder = RegistryBuilder(drifted_repo)
    builder.check()
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "atdd registry update --yes" in output, (
        "Expected fix-hint 'atdd registry update --yes' in check output.\n"
        f"Actual output:\n{output}"
    )
