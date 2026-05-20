# URN: test:govern-lifecycle:systemic-registry-drift-enforcement:E021-UNIT-001-registry-check-exits-zero-after-resync
# Acceptance: acc:govern-lifecycle:E021-UNIT-001-registry-check-exits-zero-after-resync
# WMBT: wmbt:govern-lifecycle:E021
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-001: After applying atdd registry update --yes on a drifted worktree,
RegistryBuilder.check() exits 0 with no drift for plan/_wagons.yaml,
plan/_trains.yaml, or contracts/_artifacts.yaml.

RED state: RegistryBuilder.check() does not exist. Only build_all(mode="check")
exists, and the required .check() convenience method is missing. This test
fails with AttributeError until check() is implemented.
"""
from __future__ import annotations

import yaml
import pytest
from pathlib import Path

from atdd.coach.commands.registry import RegistryBuilder


@pytest.fixture()
def synced_repo(tmp_path):
    """Minimal repo where _wagons.yaml, _trains.yaml, and _artifacts.yaml are in sync."""
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()

    wagon_dir = plan_dir / "alpha_wagon"
    wagon_dir.mkdir()
    manifest = {
        "wagon": "alpha-wagon",
        "description": "Alpha wagon",
        "theme": "commons",
        "subject": "agent:coder",
        "context": "in-lifecycle",
        "action": "acts",
        "goal": "achieves",
        "outcome": "achieved",
        "wmbt": {"total": 0},
    }
    with open(wagon_dir / "_alpha_wagon.yaml", "w") as f:
        yaml.dump(manifest, f)

    wagons_data = {
        "wagons": [
            {
                "wagon": "alpha-wagon",
                "description": "Alpha wagon",
                "theme": "commons",
                "wmbt": {"total": 0},
            }
        ]
    }
    with open(plan_dir / "_wagons.yaml", "w") as f:
        yaml.dump(wagons_data, f)

    trains_data = {"trains": []}
    with open(plan_dir / "_trains.yaml", "w") as f:
        yaml.dump(trains_data, f)

    artifacts_data = {"artifacts": []}
    with open(contracts_dir / "_artifacts.yaml", "w") as f:
        yaml.dump(artifacts_data, f)

    return tmp_path


def test_check_method_exits_zero_when_no_drift(synced_repo):
    """After build_all(apply), check() returns 0 — mirrors are in sync with source."""
    builder = RegistryBuilder(synced_repo)
    builder.build_all(mode="apply")
    exit_code = builder.check()
    assert exit_code == 0


def test_check_method_reports_no_drift_for_key_mirrors(synced_repo, capsys):
    """After apply, check() output confirms no drift for wagon/train/contract mirrors."""
    builder = RegistryBuilder(synced_repo)
    builder.build_all(mode="apply")
    capsys.readouterr()  # discard apply output
    builder.check()
    captured = capsys.readouterr()
    output = (captured.out + captured.err).lower()
    assert "no drift" in output or "in sync" in output or "✅" in output
