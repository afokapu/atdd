# URN: test:govern-lifecycle:reliable-manifest-registration:E007-INTEGRATION-001-issue-creation-commits-manifest-with-dirty-index
# Acceptance: acc:govern-lifecycle:E007-INTEGRATION-001-issue-creation-commits-manifest-with-dirty-index
# WMBT: wmbt:govern-lifecycle:E007
# Phase: RED
# Layer: integration
"""E007-INTEGRATION-001 — `atdd issue <slug>` run with unrelated staged changes
still commits the .atdd/manifest.yaml registration entry, and the registration
commit does not bundle the unrelated work.

Issue #738: when the working tree has unrelated staged files, the manifest
registration commit is skipped, leaving the issue written-but-uncommitted —
unregistered from every other checkout. This RED test drives the real
IssueManager.new() path with a dirty index (GitHub calls patched, no network)
and asserts the manifest entry is genuinely committed at HEAD, path-scoped.
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
    """An ATDD-initialised repo on a feature branch: tracked config + manifest,
    plus a tracked sibling file for the unrelated-staged-change scenario."""
    _run("git", "init", "-q", "-b", "main", cwd=tmp_path)
    _run("git", "config", "user.email", "test@example.com", cwd=tmp_path)
    _run("git", "config", "user.name", "Test User", cwd=tmp_path)
    _run("git", "config", "commit.gpgsign", "false", cwd=tmp_path)

    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()
    (atdd_dir / "config.yaml").write_text(
        "github:\n  repo: owner/demo\n  project_id: PVT_demo\n", encoding="utf-8"
    )
    (atdd_dir / "manifest.yaml").write_text("sessions: []\n", encoding="utf-8")
    (tmp_path / "plan").mkdir()
    (tmp_path / "unrelated.txt").write_text("original\n", encoding="utf-8")
    _run("git", "add", "-A", cwd=tmp_path)
    _run("git", "commit", "-q", "-m", "initial", cwd=tmp_path)
    _run("git", "checkout", "-q", "-b", branch, cwd=tmp_path)
    return tmp_path


def _head_files(repo: Path) -> list[str]:
    out = _run("git", "show", "--name-only", "--format=", "HEAD", cwd=repo).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def _staged_files(repo: Path) -> list[str]:
    out = _run("git", "diff", "--cached", "--name-only", cwd=repo).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def test_issue_creation_commits_manifest_despite_dirty_index(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    # Unrelated work: a tracked file modified and staged before `atdd issue` runs.
    (repo / "unrelated.txt").write_text("modified\n", encoding="utf-8")
    _run("git", "add", "unrelated.txt", cwd=repo)

    with patch("atdd.coach.github.GitHubClient") as mock_gh:
        client = mock_gh.return_value
        client.create_issue.return_value = 99
        client.add_issue_to_project.return_value = "ITEM_99"
        client.get_project_fields.return_value = {}

        rc = IssueManager(target_dir=repo).new(slug="demo-slug")

    assert rc == 0

    # The registration entry is committed, not merely written to the file.
    committed = _run("git", "show", "HEAD:.atdd/manifest.yaml", cwd=repo).stdout
    assert "issue_number" in committed
    assert "99" in committed

    # The registration commit is path-scoped — only the manifest.
    assert _head_files(repo) == [".atdd/manifest.yaml"]

    # The unrelated staged change is untouched — still staged, never bundled.
    assert "unrelated.txt" in _staged_files(repo)
