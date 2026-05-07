"""Fixture lock for the train-required CLI hint contract (issue #466).

The train-required error path at IssueManager.update prints a Fix block when
an implementation-type issue tries to transition past PLANNED without a Train
assigned. Issue #466 rewrote that hint to:

  C1: NOT recommend the deprecated `atdd update` invocation.
  C2: Cite `plan/_trains.yaml` as the resolver for <train_id>.
  C3: Disclose the worktree prereq (`cd` step) as step 1 of a numbered fix.

Run: PYTHONPATH=src python3 -m pytest -q \\
     src/atdd/coach/commands/tests/test_issue_train_required_hint.py -v
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from atdd.coach.commands.issue import IssueManager


pytestmark = [pytest.mark.platform]


def _setup_atdd_config(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / ".atdd"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(yaml.safe_dump({
        "github": {"repo": "owner/repo", "project_id": "PVT_test"},
    }))
    return tmp_path


def _impl_issue(status: str = "PLANNED") -> dict:
    return {
        "number": 466,
        "title": "regression: train-required hint",
        "state": "OPEN",
        "labels": [{"name": f"atdd:{status}"}, {"name": "atdd-issue"}],
        "body": "| Type | `implementation` |\n",
    }


def _capture_train_required_hint(tmp_path: Path, capsys) -> str:
    """Drive update() into the train-required branch and return stdout."""
    target = _setup_atdd_config(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _impl_issue("PLANNED")
    client.get_project_fields.return_value = {
        "ATDD Status": {"id": "f_s", "options": {"RED": "opt_red"}},
    }
    client.get_project_item_id.return_value = "item_466"
    client.get_project_item_field_values.return_value = {"ATDD Train": ""}

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(mgr, "_update_manifest_status"):
        rc = mgr.update("466", status="RED")

    assert rc == 1, "missing-train must abort (rc=1)"
    return capsys.readouterr().out


def test_hint_does_not_recommend_deprecated_atdd_update(tmp_path, capsys):
    """C1: hint must NOT cite the deprecated `atdd update` invocation."""
    out = _capture_train_required_hint(tmp_path, capsys)
    assert "atdd update" not in out, (
        "hint regressed: still recommends deprecated `atdd update`"
    )


def test_hint_cites_plan_trains_yaml_as_resolver(tmp_path, capsys):
    """C2: hint must point users at plan/_trains.yaml for <train_id>."""
    out = _capture_train_required_hint(tmp_path, capsys)
    assert "plan/_trains.yaml" in out, (
        "hint missing resolver pointer to plan/_trains.yaml"
    )


def test_hint_discloses_worktree_cd_prereq(tmp_path, capsys):
    """C3: hint must disclose the `cd` worktree prereq."""
    out = _capture_train_required_hint(tmp_path, capsys)
    assert "cd" in out, "hint missing worktree `cd` prereq"
