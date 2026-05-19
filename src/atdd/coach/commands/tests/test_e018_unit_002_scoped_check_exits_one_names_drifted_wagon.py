# URN: test:govern-lifecycle:pr-scoped-registry-drift-gate:E018-UNIT-002-scoped-check-exits-one-names-drifted-wagon
# Acceptance: acc:govern-lifecycle:E018-UNIT-002-scoped-check-exits-one-names-drifted-wagon
# WMBT: wmbt:govern-lifecycle:E018
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-002: check_wagon_registry_scoped returns has_changes=True and names the specific
drifted wagon when a changed wagon source diverges from its aggregate entry.
"""
import pytest
import yaml
from pathlib import Path


@pytest.fixture()
def temp_repo(tmp_path):
    """Repo where wagon-x source changed but its aggregate entry is stale."""
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    wagon_dir = plan_dir / "wagon_x"
    wagon_dir.mkdir()

    # Source manifest: has the new description
    manifest = {
        "wagon": "wagon-x",
        "description": "new description",
        "theme": "commons",
        "subject": "agent:coder",
        "context": "in-lifecycle",
        "action": "does x",
        "goal": "achieve x",
        "outcome": "x achieved",
    }
    with open(wagon_dir / "_wagon_x.yaml", "w") as f:
        yaml.dump(manifest, f)

    # Aggregate: has old description (drift)
    wagons_data = {
        "wagons": [
            {
                "wagon": "wagon-x",
                "description": "old description",
                "theme": "commons",
            }
        ]
    }
    with open(plan_dir / "_wagons.yaml", "w") as f:
        yaml.dump(wagons_data, f)

    return tmp_path


def test_scoped_check_detects_drift_in_changed_source(temp_repo):
    """When the changed file is a wagon source with drift, has_changes is True."""
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)
    changed = ["plan/wagon_x/_wagon_x.yaml"]
    result = builder.check_wagon_registry_scoped(changed_files=changed)

    assert result["has_changes"] is True


def test_scoped_check_names_drifted_wagon_in_output(temp_repo, capsys):
    """The error output must mention the specific wagon name."""
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)
    changed = ["plan/wagon_x/_wagon_x.yaml"]
    builder.check_wagon_registry_scoped(changed_files=changed)

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "wagon-x" in output or "wagon_x" in output


def test_scoped_check_includes_remediation_hint(temp_repo, capsys):
    """The error output must include a remediation hint (e.g. 'atdd registry update')."""
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)
    changed = ["plan/wagon_x/_wagon_x.yaml"]
    builder.check_wagon_registry_scoped(changed_files=changed)

    captured = capsys.readouterr()
    output = (captured.out + captured.err).lower()
    assert "registry update" in output or "atdd registry" in output or "run:" in output


def test_scoped_check_returns_drifted_wagon_names(temp_repo):
    """The result dict includes the drifted wagon name in drifted_wagons list."""
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)
    changed = ["plan/wagon_x/_wagon_x.yaml"]
    result = builder.check_wagon_registry_scoped(changed_files=changed)

    drifted = result.get("drifted_wagons", [])
    assert any("wagon-x" in w or "wagon_x" in w for w in drifted)
