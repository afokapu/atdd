# URN: test:place-worktrees:place-worktrees:E002-SMOKE-001-real-gc-finds-orphans-in-both-roots-and-spares-the-root
# Acceptance: acc:place-worktrees:E002-SMOKE-001-real-gc-finds-orphans-in-both-roots-and-spares-the-root
# WMBT: wmbt:place-worktrees:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral

"""E002-SMOKE-001 — real gc scans both roots and never eats the root itself.

The unit acceptance stubs `_real_worktree_paths`. This one runs `gc` against a
real git repository with a real worktree registered, so the orphan classification
is decided by actual `git worktree list` output.

The root-exclusion assertion is the load-bearing one: a hyphenated
`worktree_root` is a candidate by name, and `_is_orphan` counts only non-directory
files — so a root holding exactly one worktree that holds exactly one
`.launch_prompt.txt` matches the orphan heuristic exactly. Under `apply=True`
that is an rmtree of every worktree beneath it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.worktree_gc import gc

pytestmark = [pytest.mark.coach]

WORKTREE_ROOT = "atdd-worktrees"


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout


def _real_repo(tmp_path: Path) -> Path:
    root = tmp_path / "main"
    root.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)
    _git("config", "user.name", "Test", cwd=root)
    (root / "README.md").write_text("seed\n")
    _git("add", "README.md", cwd=root)
    _git("commit", "-q", "-m", "seed", cwd=root)
    (root / ".atdd").mkdir()
    (root / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\n"
        "github:\n"
        "  repo: owner/repo\n"
        "  default_branch: main\n"
        f"worktree_root: {WORKTREE_ROOT}\n"
    )
    return root


def _orphan(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".launch_prompt.txt").write_text("stale launch prompt\n")
    return path


def test_e002_smoke_001_real_gc_finds_orphans_in_both_roots_and_spares_the_root(tmp_path):
    root = _real_repo(tmp_path)
    configured_root = root / WORKTREE_ROOT

    legacy_orphan = _orphan(root.parent / "feat-legacy-orphan")
    configured_orphan = _orphan(configured_root / "feat-configured-orphan")

    # A REAL registered worktree, which gc must never classify as an orphan.
    real_worktree = configured_root / "feat-real-work"
    _git("worktree", "add", "-q", "-b", "feat/real-work", str(real_worktree), cwd=root)

    found = {p.resolve() for p in gc(root)}

    assert legacy_orphan.resolve() in found, "gc missed the legacy-location orphan"
    assert configured_orphan.resolve() in found, (
        "gc missed the orphan under the configured worktree_root"
    )
    assert real_worktree.resolve() not in found, (
        "gc classified a REGISTERED git worktree as an orphan"
    )
    assert configured_root.resolve() not in found, (
        f"gc classified the configured worktree_root {configured_root} as an "
        "orphan — under apply=True that removes every worktree beneath it"
    )
