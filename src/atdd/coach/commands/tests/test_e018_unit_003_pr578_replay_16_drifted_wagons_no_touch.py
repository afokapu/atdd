# URN: test:govern-lifecycle:pr-scoped-registry-drift-gate:E018-UNIT-003-pr578-replay-16-drifted-wagons-no-touch
# Acceptance: acc:govern-lifecycle:E018-UNIT-003-pr578-replay-16-drifted-wagons-no-touch
# WMBT: wmbt:govern-lifecycle:E018
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-003: PR-578 replay — 16 wagons have drifted aggregate entries but the PR
touches none of them. check_wagon_registry_scoped exits with has_changes=False and
zero absorption.
"""
import pytest
import yaml


WAGON_COUNT = 16


@pytest.fixture()
def temp_repo(tmp_path):
    """Simulate the PR-578 scenario: 16 stale wagons, PR touches none of their sources."""
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()

    wagons_registry = []
    for i in range(1, WAGON_COUNT + 1):
        slug = f"legacy-wagon-{i:02d}"
        wagon_dir = plan_dir / slug.replace("-", "_")
        wagon_dir.mkdir()
        manifest = {
            "wagon": slug,
            "description": f"Current description for wagon {i}",
            "theme": "commons",
            "subject": "agent:coder",
            "context": "in-lifecycle",
            "action": f"action {i}",
            "goal": f"goal {i}",
            "outcome": f"outcome {i}",
        }
        with open(wagon_dir / f"_{slug.replace('-', '_')}.yaml", "w") as f:
            yaml.dump(manifest, f)
        wagons_registry.append({
            "wagon": slug,
            "description": f"STALE description for wagon {i}",
            "theme": "commons",
        })

    with open(plan_dir / "_wagons.yaml", "w") as f:
        yaml.dump({"wagons": wagons_registry}, f)

    return tmp_path


def test_pr578_replay_exits_zero_with_empty_changed_files(temp_repo):
    """16 drifted wagons + zero changed files = has_changes=False (no absorption)."""
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)
    result = builder.check_wagon_registry_scoped(changed_files=[])

    assert result["has_changes"] is False


def test_pr578_replay_names_no_wagons_in_output(temp_repo, capsys):
    """Output must not mention any of the 16 drifted wagon names."""
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)
    builder.check_wagon_registry_scoped(changed_files=[])

    captured = capsys.readouterr()
    output = captured.out + captured.err
    for i in range(1, WAGON_COUNT + 1):
        assert f"legacy-wagon-{i:02d}" not in output


def test_pr578_replay_drifted_wagons_list_is_empty(temp_repo):
    """The drifted_wagons list must be empty when no wagon sources were changed."""
    from atdd.coach.commands.registry import RegistryBuilder

    builder = RegistryBuilder(temp_repo)
    result = builder.check_wagon_registry_scoped(changed_files=[])

    assert result.get("drifted_wagons", []) == []
