# URN: test:govern-lifecycle:reliable-manifest-registration:E008-UNIT-001-path-scoped-commit-isolates-index
# Acceptance: acc:govern-lifecycle:E008-UNIT-001-path-scoped-commit-isolates-index
# WMBT: wmbt:govern-lifecycle:E008
# Phase: RED
# Layer: unit
"""E008-UNIT-001 — git_commit_manifest_update commits .atdd/manifest.yaml even
when the index already holds unrelated staged changes, and the resulting commit
is path-scoped (touches only the manifest).

Issue #738: the current "refusing to commit — other staged changes exist" guard
silently aborts the manifest registration commit whenever the working tree has
unrelated staged work — which the main worktree routinely does. Because
`git commit -- <path>` is itself path-scoped, that guard prevents *registration*
without preventing *bundling*. This RED test asserts the helper commits the
manifest and leaves the unrelated staged change untouched.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.utils.git import git_commit_manifest_update

pytestmark = [pytest.mark.platform]


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args), cwd=str(cwd), capture_output=True, text=True, check=True
    )


def _init_repo(tmp_path: Path, branch: str = "feat/demo") -> Path:
    """git repo on a non-main branch with a tracked manifest + a tracked sibling."""
    _run("git", "init", "-q", "-b", "main", cwd=tmp_path)
    _run("git", "config", "user.email", "test@example.com", cwd=tmp_path)
    _run("git", "config", "user.name", "Test User", cwd=tmp_path)
    _run("git", "config", "commit.gpgsign", "false", cwd=tmp_path)

    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "manifest.yaml").write_text("sessions: []\n", encoding="utf-8")
    (tmp_path / "unrelated.txt").write_text("original\n", encoding="utf-8")
    _run("git", "add", "-A", cwd=tmp_path)
    _run("git", "commit", "-q", "-m", "initial", cwd=tmp_path)
    _run("git", "checkout", "-q", "-b", branch, cwd=tmp_path)
    return tmp_path


def _head_files(repo: Path) -> list[str]:
    """Paths changed by the HEAD commit (relative to its parent)."""
    out = _run("git", "show", "--name-only", "--format=", "HEAD", cwd=repo).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def _staged_files(repo: Path) -> list[str]:
    out = _run("git", "diff", "--cached", "--name-only", cwd=repo).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def test_path_scoped_commit_lands_with_unrelated_staged_change(tmp_path: Path) -> None:
    """git_commit_manifest_update commits the manifest and only the manifest,
    even though unrelated.txt is staged in the index."""
    repo = _init_repo(tmp_path)
    manifest = repo / ".atdd" / "manifest.yaml"

    # Pending manifest modification — a new session entry.
    manifest.write_text(
        "sessions:\n- issue_number: 99\n  slug: demo\n", encoding="utf-8"
    )
    # An unrelated tracked file, modified and staged with `git add`.
    unrelated = repo / "unrelated.txt"
    unrelated.write_text("modified\n", encoding="utf-8")
    _run("git", "add", "unrelated.txt", cwd=repo)

    sha = git_commit_manifest_update(
        path=manifest,
        message="chore(coach): register issue #99 in manifest",
        verb="atdd issue",
        repo_root=repo,
    )

    # Returns a real SHA — it must NOT raise ManifestCommitError over the
    # other staged change.
    assert sha, "expected a non-empty commit SHA"

    # The commit is path-scoped: exactly the manifest, nothing else.
    assert _head_files(repo) == [".atdd/manifest.yaml"]

    # The unrelated staged change survives — still staged, never committed.
    staged = _staged_files(repo)
    assert "unrelated.txt" in staged
    assert "unrelated.txt" not in _head_files(repo)
