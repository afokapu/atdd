"""IssueManager.update routes Projects v2 status sync through the PAT adapter.

Issue #882 / docs/coach-decomposition.md §13.4: ``atdd issue <N> --status`` must
update BOTH the label AND the Projects v2 Status field. The status sync now flows
through ``atdd.integrations.github.projects_v2.sync_status_field`` (PROJECT_TOKEN)
when the PAT is present; the ambient-auth client path is only the no-PAT fallback.

Run: PYTHONPATH=src python3 -m pytest -q \\
     src/atdd/coach/commands/tests/test_issue_update_projects_v2_adapter.py
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from atdd.coach.commands.issue import IssueManager
from atdd.integrations.github import projects_v2

pytestmark = [pytest.mark.platform]


def _setup(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / ".atdd"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(yaml.safe_dump({
        "github": {"repo": "owner/repo", "project_id": "PVT_test"},
    }))
    return tmp_path


def _issue(status: str = "RED") -> dict:
    return {
        "number": 384,
        "title": "regression",
        "state": "OPEN",
        "labels": [{"name": f"atdd:{status}"}, {"name": "atdd-issue"}],
        "body": "| Type | `cleanup` |\n",
    }


def _fields() -> dict:
    return {"ATDD Status": {"id": "field_status",
                            "options": {"GREEN": "opt_green"}}}


def test_update_prefers_pat_adapter_when_token_present(tmp_path, monkeypatch):
    """PROJECT_TOKEN set → sync via adapter; ambient client field-set skipped."""
    monkeypatch.setenv("PROJECT_TOKEN", "ghp_pat")
    target = _setup(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _issue("RED")
    client.get_project_fields.return_value = _fields()
    client.get_project_item_id.return_value = "item_abc"

    synced = []
    monkeypatch.setattr(
        projects_v2, "sync_status_field",
        lambda issue, phase, **kw: synced.append((issue, phase)),
    )

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(mgr, "_update_manifest_status"):
        rc = mgr.update("384", status="GREEN")

    assert rc == 0
    assert synced == [(384, "GREEN")]          # board synced via PAT adapter
    client.add_label.assert_called_once_with(384, ["atdd:GREEN"])  # label too
    client.set_project_field_select.assert_not_called()  # no double-write


def test_update_falls_back_to_client_without_token(tmp_path, monkeypatch):
    """No PROJECT_TOKEN → ambient client still sets the Status field."""
    monkeypatch.delenv("PROJECT_TOKEN", raising=False)
    target = _setup(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _issue("RED")
    client.get_project_fields.return_value = _fields()
    client.get_project_item_id.return_value = "item_abc"

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(mgr, "_update_manifest_status"):
        rc = mgr.update("384", status="GREEN")

    assert rc == 0
    client.set_project_field_select.assert_called_once_with(
        "item_abc", "field_status", "opt_green"
    )
