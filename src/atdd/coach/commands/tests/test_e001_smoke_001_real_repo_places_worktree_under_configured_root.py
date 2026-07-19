# URN: test:place-worktrees:place-worktrees:E001-SMOKE-001-real-repo-places-worktree-under-configured-root
# Acceptance: acc:place-worktrees:E001-SMOKE-001-real-repo-places-worktree-under-configured-root
# WMBT: wmbt:place-worktrees:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral

"""E001-SMOKE-001 — over a REAL git checkout, placement follows the config.

The unit acceptances exercise the resolver against a stubbed worktree-creation
seam. This one creates an actual git worktree at the resolved path and asks git
itself where it ended up, so the contract is pinned against real `git worktree`
behaviour rather than a mock's memory of it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.worktree_placement import resolve_worktree_path

pytestmark = [pytest.mark.coach]

SLUG = "config-driven-worktree-placement"
PREFIX = "feat"
WORKTREE_ROOT = "worktrees"


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


def test_e001_smoke_001_real_repo_places_worktree_under_configured_root(tmp_path):
    root = _real_repo(tmp_path)

    resolved = resolve_worktree_path(root, PREFIX, SLUG)
    assert resolved == (root / WORKTREE_ROOT / f"{PREFIX}-{SLUG}").resolve()

    # Create a REAL worktree there and let git report where it lives.
    resolved.parent.mkdir(parents=True, exist_ok=True)
    _git("worktree", "add", "-q", "-b", f"{PREFIX}/{SLUG}", str(resolved), cwd=root)

    listed = _git("worktree", "list", "--porcelain", cwd=root)
    registered = {
        Path(line.split(" ", 1)[1]).resolve()
        for line in listed.splitlines()
        if line.startswith("worktree ")
    }

    assert resolved in registered, (
        f"git does not report the worktree at the configured path {resolved}"
    )
    assert resolved.is_dir()

    # And nothing was left at the legacy flat-sibling location.
    legacy = root.parent / f"{PREFIX}-{SLUG}"
    assert not legacy.exists(), (
        f"a directory was created at the legacy location {legacy} despite "
        f"worktree_root: {WORKTREE_ROOT}"
    )
