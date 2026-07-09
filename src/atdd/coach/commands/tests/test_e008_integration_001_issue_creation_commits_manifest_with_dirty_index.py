# URN: test:govern-lifecycle:reliable-manifest-registration:E008-INTEGRATION-001-issue-creation-commits-manifest-with-dirty-index
# Acceptance: acc:govern-lifecycle:E008-INTEGRATION-001-issue-creation-commits-manifest-with-dirty-index
# WMBT: wmbt:govern-lifecycle:E008
# Phase: RED
# Layer: integration
"""E008-INTEGRATION-001 — `atdd issue <slug>` run with unrelated staged changes
still registers the new work item, and the registration bundles nothing from the
git index.

#1270 Slice G: the ``.atdd/manifest.yaml`` mirror was deleted — registration now
lands in the State Store, which is independent of the git index. This drives the
real IssueManager.new() path with a dirty index (GitHub calls patched, no
network) and asserts the work item is genuinely registered in the store, no
manifest is written, and the unrelated staged change is untouched.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from atdd.coach.commands.issue import IssueManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER
from atdd.state.store import StateStore

pytestmark = [pytest.mark.platform]


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args), cwd=str(cwd), capture_output=True, text=True, check=True
    )


def _init_repo(tmp_path: Path, branch: str = "feat/demo") -> Path:
    """An ATDD-initialised repo on a feature branch: tracked config, plus a
    tracked sibling file for the unrelated-staged-change scenario."""
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
    head_before = _run("git", "rev-parse", "HEAD", cwd=repo).stdout.strip()

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

    # The work item is registered in the State Store (not merely written to a file).
    db = init_state_store(start=repo)
    store = StateStore(connect(db))
    ref = store.external_refs.resolve(GITHUB_PROVIDER, "issue", "99")
    assert ref is not None, "the new issue must be registered as a store work item"
    assert store.objects.get(ref.object_uid).state == "INIT"

    # No manifest mirror is written, and registration made no git commit — the
    # unrelated staged change is untouched (still staged, never bundled).
    assert not (repo / ".atdd" / "manifest.yaml").exists()
    assert _run("git", "rev-parse", "HEAD", cwd=repo).stdout.strip() == head_before
    assert "unrelated.txt" in _staged_files(repo)
    assert _head_files(repo) != [".atdd/manifest.yaml"]
