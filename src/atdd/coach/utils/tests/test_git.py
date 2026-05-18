"""
Unit tests for atdd.coach.utils.git.git_commit_manifest_update().

URN: urn:atdd:test:coach:utils:git
WMBT: wmbt:govern-lifecycle:manifest-write-discipline
Issue: #344

Manifest-mutating CLI verbs (atdd issue, atdd update --status, atdd archive)
must commit their .atdd/manifest.yaml write atomically with the verb so a
worktree branched from main HEAD inherits the new entry. The helper enforces
the contract — every call site funnels through it.

Behavioural contract
--------------------
1. Stages only the manifest path.
2. Refuses on main unless allow_main=True (respects on-main-detection rule).
3. Commits only the manifest path — unrelated staged changes are left
   untouched, never bundled (#738: a path-scoped commit, not a refusal).
4. Returns the new commit SHA, or None if there is nothing to commit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


def _git_repo(tmp_path: Path, branch: str = "feat/test") -> Path:
    """Initialize a git repo on the given branch with a tracked manifest."""
    _run("git", "init", "-q", "-b", "main", cwd=tmp_path)
    _run("git", "config", "user.email", "test@example.com", cwd=tmp_path)
    _run("git", "config", "user.name", "Test User", cwd=tmp_path)
    _run("git", "config", "commit.gpgsign", "false", cwd=tmp_path)

    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()
    manifest = atdd_dir / "manifest.yaml"
    manifest.write_text("sessions: []\n", encoding="utf-8")
    _run("git", "add", ".atdd/manifest.yaml", cwd=tmp_path)
    _run("git", "commit", "-q", "-m", "initial manifest", cwd=tmp_path)

    if branch != "main":
        _run("git", "checkout", "-q", "-b", branch, cwd=tmp_path)
    return tmp_path


def _head_sha(repo: Path) -> str:
    return _run("git", "rev-parse", "HEAD", cwd=repo).stdout.strip()


def _head_message(repo: Path) -> str:
    return _run("git", "log", "-1", "--format=%s", cwd=repo).stdout.strip()


def _porcelain(repo: Path) -> str:
    return _run("git", "status", "--porcelain", cwd=repo).stdout


def _modify_manifest(repo: Path, marker: str = "x") -> Path:
    manifest = repo / ".atdd" / "manifest.yaml"
    manifest.write_text(f"sessions: []\nmarker: {marker}\n", encoding="utf-8")
    return manifest


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_returns_commit_sha_when_manifest_is_dirty(self, tmp_path):
        from atdd.coach.utils.git import git_commit_manifest_update

        repo = _git_repo(tmp_path)
        manifest = _modify_manifest(repo)

        sha = git_commit_manifest_update(
            path=manifest,
            message="chore(coach): register issue #1 in manifest",
            verb="atdd issue",
            repo_root=repo,
        )

        assert sha == _head_sha(repo)
        # SHA looks like a real one (40 hex chars).
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_working_tree_is_clean_after_commit(self, tmp_path):
        from atdd.coach.utils.git import git_commit_manifest_update

        repo = _git_repo(tmp_path)
        manifest = _modify_manifest(repo)

        git_commit_manifest_update(
            path=manifest,
            message="msg",
            verb="atdd issue",
            repo_root=repo,
        )

        assert _porcelain(repo) == "", (
            "expected clean tree after commit; "
            f"got: {_porcelain(repo)!r}"
        )

    def test_uses_provided_commit_message(self, tmp_path):
        from atdd.coach.utils.git import git_commit_manifest_update

        repo = _git_repo(tmp_path)
        _modify_manifest(repo)

        git_commit_manifest_update(
            path=repo / ".atdd" / "manifest.yaml",
            message="chore(coach): register issue #42 in manifest",
            verb="atdd issue",
            repo_root=repo,
        )

        assert _head_message(repo) == "chore(coach): register issue #42 in manifest"


# ---------------------------------------------------------------------------
# No-op when nothing to commit
# ---------------------------------------------------------------------------


class TestNoOp:
    def test_returns_none_when_manifest_unchanged(self, tmp_path):
        from atdd.coach.utils.git import git_commit_manifest_update

        repo = _git_repo(tmp_path)
        before_sha = _head_sha(repo)

        sha = git_commit_manifest_update(
            path=repo / ".atdd" / "manifest.yaml",
            message="msg",
            verb="atdd issue",
            repo_root=repo,
        )

        assert sha is None
        assert _head_sha(repo) == before_sha, "no commit should be created"


# ---------------------------------------------------------------------------
# Main-branch protection
# ---------------------------------------------------------------------------


class TestMainBranchGuard:
    def test_refuses_on_main_without_allow_main(self, tmp_path):
        from atdd.coach.utils.git import (
            ManifestCommitError,
            git_commit_manifest_update,
        )

        repo = _git_repo(tmp_path, branch="main")
        _modify_manifest(repo)
        before_sha = _head_sha(repo)

        with pytest.raises(ManifestCommitError, match="main"):
            git_commit_manifest_update(
                path=repo / ".atdd" / "manifest.yaml",
                message="msg",
                verb="atdd issue",
                repo_root=repo,
            )

        # No commit happened.
        assert _head_sha(repo) == before_sha

    def test_allows_main_when_explicitly_permitted(self, tmp_path):
        from atdd.coach.utils.git import git_commit_manifest_update

        repo = _git_repo(tmp_path, branch="main")
        _modify_manifest(repo)

        sha = git_commit_manifest_update(
            path=repo / ".atdd" / "manifest.yaml",
            message="msg",
            verb="atdd issue",
            repo_root=repo,
            allow_main=True,
        )

        assert sha == _head_sha(repo)


# ---------------------------------------------------------------------------
# No surprise bundling
# ---------------------------------------------------------------------------


class TestStagingIsolation:
    def test_commits_manifest_despite_other_staged_changes(self, tmp_path):
        """#738: unrelated staged changes must NOT block manifest registration.

        The `git commit -- <path>` is path-scoped, so it commits only the
        manifest; the unrelated staged change stays staged and uncommitted.
        """
        from atdd.coach.utils.git import git_commit_manifest_update

        repo = _git_repo(tmp_path)
        # Stage an unrelated file.
        other = repo / "other.txt"
        other.write_text("hello\n", encoding="utf-8")
        _run("git", "add", "other.txt", cwd=repo)

        _modify_manifest(repo)
        before_sha = _head_sha(repo)

        sha = git_commit_manifest_update(
            path=repo / ".atdd" / "manifest.yaml",
            message="msg",
            verb="atdd issue",
            repo_root=repo,
        )

        # The manifest commit landed.
        assert sha and sha == _head_sha(repo) != before_sha
        # Path-scoped: the commit touched only the manifest.
        changed = _run(
            "git", "show", "--name-only", "--format=", "HEAD", cwd=repo
        ).stdout
        assert [l.strip() for l in changed.splitlines() if l.strip()] == [
            ".atdd/manifest.yaml"
        ]
        # The unrelated change is still staged, never bundled.
        assert "A  other.txt" in _porcelain(repo)

    def test_leaves_other_unstaged_changes_alone(self, tmp_path):
        """An unstaged change to an unrelated tracked file must survive
        the commit — only the manifest gets committed."""
        from atdd.coach.utils.git import git_commit_manifest_update

        repo = _git_repo(tmp_path)
        # Add and commit an unrelated tracked file first.
        other = repo / "other.txt"
        other.write_text("hello\n", encoding="utf-8")
        _run("git", "add", "other.txt", cwd=repo)
        _run("git", "commit", "-q", "-m", "add other.txt", cwd=repo)
        # Now modify it (unstaged) and the manifest.
        other.write_text("bye\n", encoding="utf-8")
        _modify_manifest(repo)

        git_commit_manifest_update(
            path=repo / ".atdd" / "manifest.yaml",
            message="msg",
            verb="atdd issue",
            repo_root=repo,
        )

        # The manifest is committed; other.txt remains modified-unstaged.
        porcelain = _porcelain(repo)
        assert " M other.txt" in porcelain or "M  other.txt" in porcelain
        assert "manifest.yaml" not in porcelain


# ---------------------------------------------------------------------------
# Untracked file edge case
# ---------------------------------------------------------------------------


class TestUntrackedFile:
    def test_rejects_untracked_path(self, tmp_path):
        """Manifest-write discipline only applies to tracked files. If the
        manifest is untracked something is wrong upstream — surface it."""
        from atdd.coach.utils.git import (
            ManifestCommitError,
            git_commit_manifest_update,
        )

        _run("git", "init", "-q", "-b", "main", cwd=tmp_path)
        _run("git", "config", "user.email", "test@example.com", cwd=tmp_path)
        _run("git", "config", "user.name", "Test User", cwd=tmp_path)
        _run("git", "config", "commit.gpgsign", "false", cwd=tmp_path)
        # Need at least one commit so HEAD exists for branch detection.
        seed = tmp_path / "seed.txt"
        seed.write_text("seed\n", encoding="utf-8")
        _run("git", "add", "seed.txt", cwd=tmp_path)
        _run("git", "commit", "-q", "-m", "seed", cwd=tmp_path)
        _run("git", "checkout", "-q", "-b", "feat/test", cwd=tmp_path)

        atdd_dir = tmp_path / ".atdd"
        atdd_dir.mkdir()
        manifest = atdd_dir / "manifest.yaml"
        manifest.write_text("sessions: []\n", encoding="utf-8")
        # Note: NOT tracked.

        with pytest.raises(ManifestCommitError, match="track"):
            git_commit_manifest_update(
                path=manifest,
                message="msg",
                verb="atdd issue",
                repo_root=tmp_path,
            )
