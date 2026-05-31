# URN: component:govern-lifecycle:enforcement-substrate:test_core_bare_self_heal:backend:domain
# Runtime: python
# Purpose: atdd must self-heal a working-tree checkout falsely marked core.bare=true
#          before any git op, preventing the #629/#917 phantom-mass-deletion.
"""
Tests for ``ensure_repo_not_falsely_bare`` (issue #917).

``core.bare`` is a shared/common git config key. A single stray unscoped
``git config core.bare true`` (a SMOKE test in the wrong cwd, a crashed run,
an xdist worker) bleeds into ``.git/config``; the next ``git add -A`` then
treats the checkout as bare and stages the whole tree as deleted — the
phantom-mass-deletion incident (#629/#917). atdd must reset ``core.bare`` to
false at command entry, BEFORE any git op acts on the poisoned value.

These tests use a throwaway git repo under ``tmp_path`` — they never touch
the live repo.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.utils.repo import ensure_repo_not_falsely_bare

pytestmark = [pytest.mark.coach]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")
    (root / "f.txt").write_text("hello\n")
    _git(root, "add", "f.txt")
    _git(root, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "init")


def test_heals_poisoned_core_bare(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    # Poison it exactly the way the incident does.
    _git(repo, "config", "core.bare", "true")
    assert _git(repo, "config", "--get", "core.bare") == "true"

    healed = ensure_repo_not_falsely_bare(repo)

    assert healed is True
    assert _git(repo, "config", "--get", "core.bare") == "false"


def test_noop_on_clean_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    # A freshly-inited checkout is already non-bare.
    assert ensure_repo_not_falsely_bare(repo) is False


def test_noop_when_no_git_present(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert ensure_repo_not_falsely_bare(plain) is False


def test_heals_linked_worktree_via_shared_config(tmp_path: Path):
    """A linked worktree (.git is a FILE) inherits the poisoned shared config;
    healing from the worktree must clear it (core.bare is a common key)."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", str(wt), "-b", "feat")
    assert (wt / ".git").is_file()  # linked worktree gitfile

    # Poison the shared config from the primary checkout.
    _git(repo, "config", "core.bare", "true")
    assert _git(wt, "config", "--get", "core.bare") == "true"  # bled into worktree

    healed = ensure_repo_not_falsely_bare(wt)

    assert healed is True
    assert _git(wt, "config", "--get", "core.bare") == "false"
