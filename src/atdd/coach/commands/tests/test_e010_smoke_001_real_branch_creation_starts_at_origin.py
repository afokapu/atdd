# URN: test:govern-lifecycle:keep-local-main-current-branch-from-origin:E010-SMOKE-001-real-branch-creation-starts-at-origin
# Acceptance: acc:govern-lifecycle:E010-SMOKE-001-real-branch-creation-starts-at-origin
# WMBT: wmbt:govern-lifecycle:E010
# Phase: SMOKE
# Layer: backend.integration
# Assertion: behavioral

"""E010-SMOKE-001 — In a real git repo with a simulated stale local default
branch, BranchManager.branch() creates the new worktree at origin/<default>
HEAD, not the stale local ref.

This test builds two real git repos (bare remote + local clone), advances the
remote by one commit, then leaves the local main behind.  BranchManager.branch()
must create the new branch from origin/main (C2), not stale local main (C1).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.coach]


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True, text=True,
        cwd=cwd, check=True,
    )


def _setup_real_repo(tmp_path: Path):
    """
    Build:
        tmp_path/bare/    — bare remote
        tmp_path/main/    — local clone (worktree-ready primary checkout)

    Timeline:
        C1 — initial commit on remote + cloned to local main
        C2 — second commit pushed to remote ONLY (local main stays at C1)

    Returns (main_wt, remote_commit_sha) where main_wt is the local main
    worktree path.
    """
    bare = tmp_path / "bare"
    bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    main_wt = tmp_path / "main"
    main_wt.mkdir()
    subprocess.run(["git", "clone", str(bare), str(main_wt)], check=True, capture_output=True)

    _git("config", "user.email", "test@example.com", cwd=main_wt)
    _git("config", "user.name", "Test", cwd=main_wt)

    # C1: initial commit
    (main_wt / "README.md").write_text("init\n")
    _git("add", "README.md", cwd=main_wt)
    _git("commit", "-m", "C1 initial", cwd=main_wt)
    _git("push", "origin", "main", cwd=main_wt)

    # C2: second commit — push to remote, do NOT pull into local main
    # Use a temp clone to push C2 without advancing local main
    tmp_clone = tmp_path / "_tmp_clone"
    subprocess.run(["git", "clone", str(bare), str(tmp_clone)], check=True, capture_output=True)
    _git("config", "user.email", "test@example.com", cwd=tmp_clone)
    _git("config", "user.name", "Test", cwd=tmp_clone)
    (tmp_clone / "EXTRA.md").write_text("extra\n")
    _git("add", "EXTRA.md", cwd=tmp_clone)
    _git("commit", "-m", "C2 remote-only", cwd=tmp_clone)
    _git("push", "origin", "main", cwd=tmp_clone)

    # Fetch origin in main_wt so origin/main is updated, but DO NOT pull
    _git("fetch", "origin", "main", cwd=main_wt)

    # Verify local main is behind origin/main
    local_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=main_wt
    ).stdout.strip()
    origin_sha = subprocess.run(
        ["git", "rev-parse", "origin/main"], capture_output=True, text=True, cwd=main_wt
    ).stdout.strip()
    assert local_sha != origin_sha, "Setup error: local main should be behind origin/main"

    return main_wt, origin_sha


def _make_manifest_and_config(repo_root: Path, issue_number: int, slug: str) -> None:
    manifest = {"sessions": [{"issue_number": issue_number, "slug": slug, "type": "implementation"}]}
    (repo_root / ".atdd").mkdir(exist_ok=True)
    (repo_root / ".atdd" / "manifest.yaml").write_text(yaml.dump(manifest))
    (repo_root / ".atdd" / "config.yaml").write_text(
        "github:\n  repo: owner/repo\n  default_branch: main\n"
    )


def test_new_branch_starts_at_origin_main_not_stale_local(tmp_path):
    """New worktree merge-base must be origin/main (C2), not stale local main (C1)."""
    main_wt, origin_sha = _setup_real_repo(tmp_path)
    _make_manifest_and_config(main_wt, issue_number=99, slug="smoke-test-feature")

    from unittest.mock import patch
    from atdd.coach.commands.branch import BranchManager

    # Patch GitHub calls (no real GitHub needed for this structural test)
    with patch.object(BranchManager, "_create_draft_pr", return_value=None), \
         patch("atdd.coach.commands.branch.detect_worktree_layout", return_value="worktree-ready"), \
         patch("atdd.coach.commands.branch.write_workspace", return_value=None), \
         patch("atdd.coach.commands.branch.GitHubClient"):
        mgr = BranchManager(target_dir=main_wt)
        result = mgr.branch(issue_number=99)

    assert result == 0, "BranchManager.branch() should return 0 on success"

    # The new worktree should exist
    new_wt = tmp_path / "feat-smoke-test-feature"
    assert new_wt.exists(), f"Expected worktree at {new_wt}"

    # The new branch's HEAD should match origin/main (C2), not stale local (C1)
    new_branch_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=new_wt,
    ).stdout.strip()

    assert new_branch_sha == origin_sha, (
        f"New branch HEAD={new_branch_sha!r} should match origin/main={origin_sha!r}. "
        "BranchManager.branch() appears to be cutting from stale local main rather than "
        "origin/main."
    )
