# URN: test:govern-lifecycle:reliable-manifest-registration:E008-INTEGRATION-002-registration-failure-exits-non-zero
# Acceptance: acc:govern-lifecycle:E008-INTEGRATION-002-registration-failure-exits-non-zero
# WMBT: wmbt:govern-lifecycle:E008
# Phase: RED
# Layer: integration
"""E008-INTEGRATION-002 — when the registration write genuinely cannot complete,
`atdd issue` exits non-zero with a clear error and never reports success with an
unregistered issue.

Issue #738 (preserved on the State Store after #1270 Slice G deleted the manifest
mirror): a "success" with an unregistered issue is silently wrong. This drives
IssueManager.new() with the store-registration write forced to fail and asserts
the verb exits non-zero, names the failed registration, and does not print its
success summary.
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


def _init_repo(tmp_path: Path, branch: str = "feat/demo") -> Path:
    """An ATDD-initialised repo (tracked config.yaml) on a feature branch."""
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
    return tmp_path


def test_registration_failure_exits_non_zero(tmp_path: Path, capsys) -> None:
    repo = _init_repo(tmp_path)

    with patch("atdd.coach.github.GitHubClient") as mock_gh, \
         patch.object(IssueManager, "_store_create_work_item", return_value=False):
        client = mock_gh.return_value
        client.create_issue.return_value = 99
        client.add_issue_to_project.return_value = "ITEM_99"
        client.get_project_fields.return_value = {}

        rc = IssueManager(target_dir=repo).new(slug="demo-slug")

    out = capsys.readouterr().out

    # Never report success with an unregistered issue.
    assert rc != 0

    # The error explicitly names the failed registration and that it is NOT registered.
    assert "NOT registered" in out

    # The success summary (`Created #99 with N WMBTs`) must not be printed.
    assert "WMBTs" not in out
