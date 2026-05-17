# URN: test:govern-lifecycle:reliable-manifest-registration:E007-INTEGRATION-002-registration-failure-exits-non-zero
# Acceptance: acc:govern-lifecycle:E007-INTEGRATION-002-registration-failure-exits-non-zero
# WMBT: wmbt:govern-lifecycle:E007
# Phase: RED
# Layer: integration
"""E007-INTEGRATION-002 — when the manifest registration commit genuinely cannot
complete, `atdd issue` exits non-zero with a clear error and never reports
success with an unregistered issue.

Issue #738: a "success" with an uncommitted manifest entry is silently wrong.
This RED test drives IssueManager.new() against a repo where the registration
commit genuinely fails (the manifest is untracked) and asserts the verb exits
non-zero, names the failure, and does not print its success summary.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from atdd.coach.commands.issue import IssueManager

pytestmark = [pytest.mark.platform]


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args), cwd=str(cwd), capture_output=True, text=True, check=True
    )


def _init_repo_untracked_manifest(tmp_path: Path, branch: str = "feat/demo") -> Path:
    """An ATDD-initialised repo whose .atdd/manifest.yaml exists on disk but is
    NOT tracked by git — the registration commit genuinely cannot complete."""
    _run("git", "init", "-q", "-b", "main", cwd=tmp_path)
    _run("git", "config", "user.email", "test@example.com", cwd=tmp_path)
    _run("git", "config", "user.name", "Test User", cwd=tmp_path)
    _run("git", "config", "commit.gpgsign", "false", cwd=tmp_path)

    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()
    (atdd_dir / "config.yaml").write_text(
        "github:\n  repo: owner/demo\n  project_id: PVT_demo\n", encoding="utf-8"
    )
    (tmp_path / "plan").mkdir()
    _run("git", "add", ".atdd/config.yaml", cwd=tmp_path)
    _run("git", "commit", "-q", "-m", "initial", cwd=tmp_path)
    _run("git", "checkout", "-q", "-b", branch, cwd=tmp_path)

    # Manifest exists on disk (so the write succeeds) but is left untracked.
    (atdd_dir / "manifest.yaml").write_text("sessions: []\n", encoding="utf-8")
    return tmp_path


def test_registration_failure_exits_non_zero(tmp_path: Path, capsys) -> None:
    repo = _init_repo_untracked_manifest(tmp_path)

    with patch("atdd.coach.github.GitHubClient") as mock_gh:
        client = mock_gh.return_value
        client.create_issue.return_value = 99
        client.add_issue_to_project.return_value = "ITEM_99"
        client.get_project_fields.return_value = {}

        rc = IssueManager(target_dir=repo).new(slug="demo-slug")

    out = capsys.readouterr().out

    # Never report success with an unregistered issue.
    assert rc != 0

    # The error explicitly names the manifest and the failed registration.
    assert "manifest.yaml" in out

    # The success summary (`Created #99 with N WMBTs`) must not be printed.
    assert "WMBTs" not in out
