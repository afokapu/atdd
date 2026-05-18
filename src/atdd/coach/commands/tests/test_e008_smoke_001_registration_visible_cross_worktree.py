# URN: test:govern-lifecycle:reliable-manifest-registration:E008-SMOKE-001-registration-visible-cross-worktree
# Acceptance: acc:govern-lifecycle:E008-SMOKE-001-registration-visible-cross-worktree
# WMBT: wmbt:govern-lifecycle:E008
# Phase: SMOKE
# Layer: smoke
"""E008-SMOKE-001 — against real git infrastructure, a manifest registration
commit made with an unrelated staged change in the index is visible from a
separate checkout of the branch and carries only the manifest path.

This is the SMOKE-phase verification for #738: no subprocess mocking. A real
git repository, a real `git add`-staged sibling file, and a real *linked git
worktree* exercise the cross-checkout visibility that the bug broke — an issue
written-but-uncommitted is invisible from every other checkout.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.utils.git import git_commit_manifest_update

pytestmark = [pytest.mark.platform]


def _git(*args: str, cwd: Path) -> str:
    """Run a real git command, failing loudly on error."""
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    ).stdout


def _init_repo(tmp_path: Path) -> Path:
    """A real git repo: initial commit on main, then a feature branch."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    _git("config", "commit.gpgsign", "false", cwd=repo)

    (repo / ".atdd").mkdir()
    (repo / ".atdd" / "manifest.yaml").write_text("sessions: []\n", encoding="utf-8")
    (repo / "unrelated.txt").write_text("original\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "initial", cwd=repo)
    _git("checkout", "-q", "-b", "feat/demo", cwd=repo)
    return repo


def _head_files(repo: Path) -> list[str]:
    out = _git("show", "--name-only", "--format=", "HEAD", cwd=repo)
    return [line.strip() for line in out.splitlines() if line.strip()]


def test_registration_is_visible_from_a_linked_worktree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    manifest = repo / ".atdd" / "manifest.yaml"

    # A real linked worktree tracking the same feature branch (detached at its
    # tip, since a branch cannot be checked out in two worktrees at once).
    sibling = tmp_path / "sibling"
    _git("worktree", "add", "--detach", str(sibling), "feat/demo", cwd=repo)

    # The pending manifest write — a new session entry.
    manifest.write_text(
        "sessions:\n- issue_number: 99\n  slug: demo\n  status: INIT\n",
        encoding="utf-8",
    )
    # An unrelated tracked file, really modified and `git add`-staged.
    (repo / "unrelated.txt").write_text("modified\n", encoding="utf-8")
    _git("add", "unrelated.txt", cwd=repo)

    sha = git_commit_manifest_update(
        path=manifest,
        message="chore(coach): register issue #99 in manifest",
        verb="atdd issue",
        repo_root=repo,
    )
    assert sha, "expected a real commit SHA from the registration commit"

    # The registration commit is path-scoped — only the manifest.
    assert _head_files(repo) == [".atdd/manifest.yaml"]

    # Refresh the sibling worktree to the branch tip.
    _git("checkout", "-q", "--detach", sha, cwd=sibling)

    # The registration is visible cross-checkout: the sibling sees the entry.
    sibling_manifest = (sibling / ".atdd" / "manifest.yaml").read_text(encoding="utf-8")
    assert "issue_number: 99" in sibling_manifest

    # The unrelated staged change was NOT committed — the sibling, at the tip,
    # still sees the original content.
    assert (sibling / "unrelated.txt").read_text(encoding="utf-8") == "original\n"

    # And the original worktree still has it staged, uncommitted.
    staged = _git("diff", "--cached", "--name-only", cwd=repo)
    assert "unrelated.txt" in staged

    _git("worktree", "remove", "--force", str(sibling), cwd=repo)
