"""Fixture lock for the PR-existence gate at INIT → PLANNED (issue #478).

The PLANNED transition assumes the branch is reviewable. Since `atdd branch`
defers PR creation (Phase 1), the gate has to live at the next step in the
lifecycle — `atdd issue <N> --status PLANNED` — and it must satisfy the
#467 hint contract (numbered prereqs, runnable as printed, no deprecated
CLI form).

Three fixtures cover:
  (a) PR exists for the issue's branch → transition succeeds.
  (b) No PR for the branch → transition blocked with structured Fix hint.
  (c) ``--force`` overrides with a ``::warning::`` line and proceeds.

Run: PYTHONPATH=src python3 -m pytest -q \\
     src/atdd/coach/commands/tests/test_issue_planned_pr_gate.py -v
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
    (cfg_dir / "manifest.yaml").write_text(yaml.safe_dump({
        "version": "2.0",
        "sessions": [
            # #1051: the PLANNED PR-gate resolves the branch from the local
            # manifest (the Projects v2 "ATDD Branch" board read is retired).
            {"id": "478", "slug": "478-branch-pr-empty",
             "issue_number": 478, "type": "cleanup", "status": "INIT",
             "branch": "chore/478-branch-pr-empty"},
        ],
    }))
    return tmp_path


def _init_issue() -> dict:
    return {
        "number": 478,
        "title": "branch-pr-empty",
        "state": "OPEN",
        "labels": [{"name": "atdd:INIT"}, {"name": "atdd-issue"}],
        "body": "| Type | `cleanup` |\n",
    }


def _fresh_mgr_with_client(tmp_path: Path) -> tuple:
    target = _setup_atdd_config(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _init_issue()
    client.get_project_fields.return_value = {
        "ATDD Status": {"id": "f_s", "options": {"PLANNED": "opt_planned"}},
    }
    client.get_project_item_id.return_value = "item_478"
    client.get_project_item_field_values.return_value = {
        "ATDD Branch": "chore/478-branch-pr-empty",
    }
    return mgr, client


# ---------------------------------------------------------------------------
# Fixture (a): PR exists → transition succeeds
# ---------------------------------------------------------------------------

def test_planned_transition_succeeds_when_pr_exists(tmp_path, capsys):
    mgr, client = _fresh_mgr_with_client(tmp_path)

    def gh_run(cmd, **kwargs):
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        if cmd[:3] == ["gh", "pr", "list"]:
            proc.stdout = "478\n"
        else:
            proc.stdout = ""
        return proc

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(mgr, "_update_manifest_status"), \
         patch("atdd.coach.commands.issue.subprocess.run",
               side_effect=gh_run):
        rc = mgr.update("478", status="PLANNED")

    assert rc == 0, "PLANNED transition must succeed when a PR exists"
    out = capsys.readouterr().out
    assert "PR: #478 found for branch" in out
    assert "::warning::" not in out
    assert "Error: No open PR found" not in out


# ---------------------------------------------------------------------------
# Fixture (b): no PR → transition blocked with structured hint
# ---------------------------------------------------------------------------

def test_planned_transition_blocked_when_no_pr(tmp_path, capsys):
    mgr, client = _fresh_mgr_with_client(tmp_path)

    def gh_run(cmd, **kwargs):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        proc.stderr = ""
        return proc

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(mgr, "_update_manifest_status"), \
         patch("atdd.coach.commands.issue.subprocess.run",
               side_effect=gh_run):
        rc = mgr.update("478", status="PLANNED")

    assert rc == 1, "PLANNED transition must abort when no PR exists"
    out = capsys.readouterr().out
    assert "Error: No open PR found" in out
    assert "Fix:" in out
    # #467 contract — numbered prereqs, runnable as printed
    assert "1." in out and "2." in out and "3." in out and "4." in out
    assert "atdd pr 478" in out
    assert "atdd issue 478 --status PLANNED" in out
    # No deprecated CLI form
    assert "atdd update" not in out
    # Bypass surfaced
    assert "--force" in out


# ---------------------------------------------------------------------------
# Fixture (c): --force override accepted with ::warning::
# ---------------------------------------------------------------------------

def test_planned_transition_force_override_emits_warning(tmp_path, capsys):
    mgr, client = _fresh_mgr_with_client(tmp_path)

    def gh_run(cmd, **kwargs):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        proc.stderr = ""
        return proc

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(mgr, "_update_manifest_status"), \
         patch("atdd.coach.commands.issue.subprocess.run",
               side_effect=gh_run):
        rc = mgr.update("478", status="PLANNED", force=True)

    assert rc == 0, "PLANNED transition with --force must proceed"
    out = capsys.readouterr().out
    assert "::warning::PR-existence gate bypassed" in out
    assert "Error: No open PR found" not in out
