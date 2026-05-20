# Acceptance: acc:integration-hardening:Y006-SMOKE-001-init-force-in-linked-worktree-writes-config-worktree-file
"""SMOKE test for Y006: real git repo verifies core.hooksPath ends up in config.worktree.

Background: _install_hooks must write 'git config --worktree core.hooksPath <path>'
when run inside a linked worktree. This test creates a real tmp_path git repo with a
linked worktree and verifies that after _install_hooks runs:
  - The shared .git/config does NOT contain hooksPath
  - The worktree-local config.worktree DOES contain hooksPath

Test hygiene: all git operations use 'git -C <path>' so no live-repo mutations occur.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.initializer import ProjectInitializer

pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[6]


def _git(path: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a git command rooted at path; never touches the invoking process's repo."""
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
    )


def _init_repo(path: Path) -> None:
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(path)],
        check=True,
        capture_output=True,
    )
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    # Initial commit so worktrees can be added
    (path / "README.md").write_text("init\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init", "--allow-empty-message")


def test_init_force_in_linked_worktree_writes_config_worktree(tmp_path: Path) -> None:
    """Y006-SMOKE-001: core.hooksPath lands in config.worktree, not shared .git/config."""
    main_repo = tmp_path / "main"
    main_repo.mkdir()
    _init_repo(main_repo)

    # Enable extensions.worktreeConfig (the fix must enable this if absent, but
    # we set it here to ensure the --worktree flag works in git)
    _git(main_repo, "config", "extensions.worktreeConfig", "true")

    # Add a linked worktree
    linked = tmp_path / "linked"
    result = subprocess.run(
        ["git", "-C", str(main_repo), "worktree", "add", str(linked), "-b", "feat/x"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"git worktree add failed: {result.stderr}"
    assert linked.is_dir(), f"linked worktree directory was not created: {linked}"

    # Run _install_hooks against the linked worktree (no subprocess monkeypatching)
    ini = ProjectInitializer(target_dir=linked)
    # Provide a minimal template dir so the hook copy loop has something to process
    # We patch only the package_root to avoid needing the installed template dir
    tmpl_dir = tmp_path / "templates" / "hooks"
    tmpl_dir.mkdir(parents=True)
    (tmpl_dir / "pre-commit").write_text("#!/bin/sh\nexit 0\n")

    import unittest.mock as mock
    with mock.patch.object(ini, "package_root", tmp_path):
        ini._install_hooks(force=True)

    # Assert: shared .git/config must NOT contain hooksPath
    shared_config = main_repo / ".git" / "config"
    shared_content = shared_config.read_text()
    assert "hooksPath" not in shared_content, (
        f"FAIL: core.hooksPath leaked into shared .git/config:\n{shared_content}"
    )

    # Assert: worktree-local config.worktree DOES contain hooksPath
    # Find the worktrees directory: .git/worktrees/<name>/config.worktree
    worktrees_dir = main_repo / ".git" / "worktrees"
    assert worktrees_dir.is_dir(), f".git/worktrees/ does not exist after worktree add"

    wt_dirs = list(worktrees_dir.iterdir())
    assert wt_dirs, f"No worktree entries found in {worktrees_dir}"

    wt_config = wt_dirs[0] / "config.worktree"
    assert wt_config.exists(), (
        f"config.worktree not found at {wt_config}; "
        f"worktree entry contents: {list(wt_dirs[0].iterdir())}"
    )

    wt_content = wt_config.read_text()
    assert "hooksPath" in wt_content, (
        f"FAIL: core.hooksPath not found in config.worktree:\n{wt_content}"
    )

    # Assert: reading core.hooksPath from linked worktree resolves (worktree-local read)
    linked_hooks = _git(linked, "config", "--get", "core.hooksPath")
    assert linked_hooks.returncode == 0 and linked_hooks.stdout.strip(), (
        f"FAIL: 'git config --get core.hooksPath' from linked worktree failed: "
        f"rc={linked_hooks.returncode} stdout={linked_hooks.stdout!r}"
    )

    # Assert: reading core.hooksPath from main worktree returns empty (shared config is clean)
    main_hooks = _git(main_repo, "config", "--get", "core.hooksPath")
    assert main_hooks.returncode != 0 or main_hooks.stdout.strip() == "", (
        f"FAIL: core.hooksPath should not be set in the main worktree's shared config; "
        f"got: {main_hooks.stdout!r}"
    )
