# URN: test:govern-lifecycle:pr-scoped-registry-drift-gate:E018-UNIT-001-scoped-check-exits-zero-no-wagon-sources
# Acceptance: acc:govern-lifecycle:E018-UNIT-001-scoped-check-exits-zero-no-wagon-sources
# WMBT: wmbt:govern-lifecycle:E018
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-001: check_wagon_registry_scoped exits 0 (has_changes=False) when changed_files
is empty, even when the repo has pre-existing aggregate drift.
"""
import pytest
import yaml
from pathlib import Path


@pytest.fixture()
def temp_repo(tmp_path):
    """Repo with a stale _wagons.yaml entry (repo-wide drift) but the PR touches nothing."""
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    wagon_dir = plan_dir / "my_wagon"
    wagon_dir.mkdir()

    # Wagon source manifest: has new description
    manifest = {
        "wagon": "my-wagon",
        "description": "New description (source of truth)",
        "theme": "commons",
        "subject": "agent:coder",
        "context": "in-lifecycle",
        "action": "does things",
        "goal": "achieve things",
        "outcome": "things achieved",
    }
    with open(wagon_dir / "_my_wagon.yaml", "w") as f:
        yaml.dump(manifest, f)

    # Aggregate entry: has stale description (drift exists)
    wagons_data = {
        "wagons": [
            {
                "wagon": "my-wagon",
                "description": "Old description (stale)",
                "theme": "commons",
            }
        ]
    }
    with open(plan_dir / "_wagons.yaml", "w") as f:
        yaml.dump(wagons_data, f)

    return tmp_path


def test_scoped_check_trivial_pass_when_no_wagon_sources_changed(temp_repo):
    """With an empty changed_files list, the scoped check passes regardless of repo drift."""
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)
    result = builder.check_wagon_registry_scoped(changed_files=[])

    assert result["has_changes"] is False


def test_scoped_check_trivial_pass_prints_no_wagon_names(temp_repo, capsys):
    """Output for empty changed_files must not mention any wagon name."""
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)
    builder.check_wagon_registry_scoped(changed_files=[])

    captured = capsys.readouterr()
    assert "my-wagon" not in captured.out
    assert "my-wagon" not in captured.err


def test_scoped_check_trivial_pass_prints_notice(temp_repo, capsys):
    """Output for empty changed_files must contain a 'no wagon sources' notice."""
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)
    builder.check_wagon_registry_scoped(changed_files=[])

    captured = capsys.readouterr()
    output = (captured.out + captured.err).lower()
    assert "no wagon sources" in output or "no wagon" in output or "trivial" in output or "nothing to check" in output
