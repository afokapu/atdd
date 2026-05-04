"""
Regression tests for IssueManager.update fallback when ProjectV2 access denied.

Issue #384: GHA token without `projects: write` (or org-disabled Projects
access) hard-fails the auto-phase workflow before the label swap runs. With
the narrow try/except patch around the ProjectV2 GraphQL calls, denied access
logs a warning and continues with label-only sync.

Three branches covered:
1. denied  — "Resource not accessible by integration" → label swap runs, rc=0
2. granted — happy path: label swap AND ProjectV2 field updates both run
3. other   — non-matching GitHubClientError still aborts (rc=1, no label swap)

Run: PYTHONPATH=src python3 -m pytest -q \\
     src/atdd/coach/commands/tests/test_issue_update_fallback.py -v
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from atdd.coach.commands.issue import IssueManager
from atdd.coach.github import GitHubClientError


pytestmark = [pytest.mark.platform]


def _setup_atdd_config(tmp_path: Path) -> Path:
    """Create a minimal .atdd/config.yaml so _check_initialized passes."""
    cfg_dir = tmp_path / ".atdd"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(yaml.safe_dump({
        "github": {"repo": "owner/repo", "project_id": "PVT_test"},
    }))
    return tmp_path


def _make_issue(status: str = "RED") -> dict:
    """Fake gh-issue dict with cleanup type (train-optional)."""
    return {
        "number": 384,
        "title": "regression: auto-phase",
        "state": "OPEN",
        "labels": [{"name": f"atdd:{status}"}, {"name": "atdd-issue"}],
        "body": "| Type | `cleanup` |\n",
    }


def _make_fields_dict() -> dict:
    return {
        "ATDD Status": {
            "id": "field_status",
            "options": {"GREEN": "opt_green", "SMOKE": "opt_smoke"},
        },
    }


# ---------------------------------------------------------------------------
# Branch 1: denied → label-only fallback succeeds
# ---------------------------------------------------------------------------

def test_denied_falls_back_to_label_only_via_get_project_fields(tmp_path):
    """get_project_fields raises access-denied → label swap runs, rc=0."""
    target = _setup_atdd_config(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _make_issue("RED")
    client.get_project_fields.side_effect = GitHubClientError(
        "Resource not accessible by integration"
    )

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(mgr, "_update_manifest_status"):
        rc = mgr.update("384", status="GREEN")

    assert rc == 0, "denied access should fall back, not abort"
    client.add_label.assert_called_once_with(384, ["atdd:GREEN"])
    client.set_project_field_select.assert_not_called()


def test_denied_falls_back_to_label_only_via_get_project_item_id(tmp_path):
    """get_project_item_id raises access-denied → label swap runs, rc=0."""
    target = _setup_atdd_config(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _make_issue("RED")
    client.get_project_fields.return_value = _make_fields_dict()
    client.get_project_item_id.side_effect = GitHubClientError(
        "Resource not accessible by integration"
    )

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(mgr, "_update_manifest_status"):
        rc = mgr.update("384", status="GREEN")

    assert rc == 0
    client.add_label.assert_called_once_with(384, ["atdd:GREEN"])
    client.set_project_field_select.assert_not_called()


def test_denied_logs_warning_with_remediation(tmp_path, caplog):
    """Warning log must include actionable remediation hint."""
    import logging
    caplog.set_level(logging.WARNING, logger="atdd.coach.commands.issue")

    target = _setup_atdd_config(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _make_issue("RED")
    client.get_project_fields.side_effect = GitHubClientError(
        "Resource not accessible by integration"
    )

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(mgr, "_update_manifest_status"):
        mgr.update("384", status="GREEN")

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("ProjectV2" in m for m in warnings), warnings
    # Issue #404 changed the remediation hint: GITHUB_TOKEN cannot grant
    # projects:write, so the actionable upgrade path is now the optional
    # PROJECT_TOKEN PAT, not the workflow permissions block.
    assert any("PROJECT_TOKEN" in m for m in warnings), warnings


# ---------------------------------------------------------------------------
# Branch 2: granted → both label swap and field updates run
# ---------------------------------------------------------------------------

def test_granted_runs_both_label_and_project_field(tmp_path):
    target = _setup_atdd_config(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _make_issue("RED")
    client.get_project_fields.return_value = _make_fields_dict()
    client.get_project_item_id.return_value = "item_abc"

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(mgr, "_update_manifest_status"):
        rc = mgr.update("384", status="GREEN")

    assert rc == 0
    client.add_label.assert_called_once_with(384, ["atdd:GREEN"])
    client.set_project_field_select.assert_called_once_with(
        "item_abc", "field_status", "opt_green"
    )


# ---------------------------------------------------------------------------
# Branch 3: other GitHubClientError still aborts
# ---------------------------------------------------------------------------

def test_non_matching_github_error_aborts(tmp_path, capsys):
    """Non-access-denied GitHubClientError must still abort (rc=1)."""
    target = _setup_atdd_config(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _make_issue("RED")
    client.get_project_fields.side_effect = GitHubClientError(
        "Network error: connection reset by peer"
    )

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(mgr, "_update_manifest_status"):
        rc = mgr.update("384", status="GREEN")

    assert rc == 1, "unrelated GitHubClientError must not be swallowed"
    client.add_label.assert_not_called()


# ---------------------------------------------------------------------------
# Branch 4: item_id None on access-denied does not trigger "not found" error
# ---------------------------------------------------------------------------

def test_access_denied_does_not_print_not_found_in_project(tmp_path, capsys):
    """Sentinel flag must distinguish 'denied' from 'missing in Project'."""
    target = _setup_atdd_config(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _make_issue("RED")
    client.get_project_fields.side_effect = GitHubClientError(
        "Resource not accessible by integration"
    )

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(mgr, "_update_manifest_status"):
        rc = mgr.update("384", status="GREEN")

    out = capsys.readouterr().out
    assert "not found in Project" not in out, (
        "access-denied must not be reported as missing in Project"
    )
    assert rc == 0
