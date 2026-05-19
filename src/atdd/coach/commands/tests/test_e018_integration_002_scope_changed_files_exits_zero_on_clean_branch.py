# URN: test:govern-lifecycle:pr-scoped-registry-drift-gate:E018-INTEGRATION-002-scope-changed-files-exits-zero-on-clean-branch
# Acceptance: acc:govern-lifecycle:E018-INTEGRATION-002-scope-changed-files-exits-zero-on-clean-branch
# WMBT: wmbt:govern-lifecycle:E018
# Phase: GREEN
# Layer: backend.integration
"""
AC-INTEGRATION-002: update_registries(check=True, scope='changed-files') returns 0
on a repo where git diff main..HEAD shows no changed wagon sources.
"""
import pytest
import subprocess
import sys
import yaml
from pathlib import Path
from unittest.mock import patch


@pytest.fixture()
def temp_repo(tmp_path):
    """A minimal repo: _wagons.yaml in sync, no diff from main."""
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    wagon_dir = plan_dir / "alpha_wagon"
    wagon_dir.mkdir()

    manifest = {
        "wagon": "alpha-wagon",
        "description": "Alpha wagon description",
        "theme": "commons",
        "subject": "agent:coder",
        "context": "in-lifecycle",
        "action": "acts",
        "goal": "achieves",
        "outcome": "achieved",
    }
    with open(wagon_dir / "_alpha_wagon.yaml", "w") as f:
        yaml.dump(manifest, f)

    wagons_data = {"wagons": []}
    with open(plan_dir / "_wagons.yaml", "w") as f:
        yaml.dump(wagons_data, f)

    return tmp_path


def test_scope_changed_files_returns_zero_when_diff_empty(temp_repo):
    """update_registries with scope='changed-files' returns 0 when git diff is empty."""
    from atdd.cli import ATDDCoach

    coach = ATDDCoach(repo_root=temp_repo)

    # Patch git diff to return empty (no wagon sources changed)
    with patch("subprocess.run") as mock_run:
        from unittest.mock import MagicMock
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        result = coach.update_registries(check=True, scope="changed-files")

    assert result == 0


def test_scope_changed_files_kwarg_accepted():
    """update_registries must accept a 'scope' keyword argument without raising TypeError."""
    from atdd.cli import ATDDCoach

    coach = ATDDCoach(repo_root=Path("/tmp"))

    import inspect
    sig = inspect.signature(coach.update_registries)
    assert "scope" in sig.parameters, (
        "update_registries does not accept 'scope' parameter — "
        "add scope: str = None to the signature"
    )
