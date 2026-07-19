# URN: test:place-worktrees:place-worktrees:Y001-SMOKE-001-real-relocation-moves-git-and-store-together
# Acceptance: acc:place-worktrees:Y001-SMOKE-001-real-relocation-moves-git-and-store-together
# WMBT: wmbt:place-worktrees:Y001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral

"""Y001-SMOKE-001 — a real relocation moves git and the store together.

Y001-UNIT-001 pins the ROLLBACK by injecting a store-write failure. This pins the
happy path over real machinery: a real `git worktree move`, a real State Store
write, and uncommitted work that has to survive both.

Decision 3 on #1524 was that a worktree can move itself. The empirical check
behind that decision lives here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.worktree_placement import relocate_worktree
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.coach]

ISSUE = 1524
SLUG = "config-driven-worktree-placement"
PREFIX = "feat"
WORKTREE_ROOT = "worktrees"


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout


def _real_repo(tmp_path: Path) -> tuple[Path, Path]:
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

    # A real worktree at the LEGACY location, carrying uncommitted work.
    legacy = root.parent / f"{PREFIX}-{SLUG}"
    _git("worktree", "add", "-q", "-b", f"{PREFIX}/{SLUG}", str(legacy), cwd=root)
    (legacy / "uncommitted.txt").write_text("work that must survive\n")

    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        store.objects.upsert(
            SLUG,
            WORK_ITEM_KIND,
            state="RED",
            data={
                "issue_number": ISSUE,
                "type": "implementation",
                "branch": f"{PREFIX}/{SLUG}",
                "worktree_path": str(legacy),
            },
        )
        store.external_refs.link(SLUG, GITHUB_PROVIDER, "issue", str(ISSUE))
        conn.commit()
    finally:
        conn.close()
    return root, legacy


def _binding(root: Path) -> str | None:
    conn = connect(init_state_store(start=root))
    try:
        obj = StateStore(conn).objects.get(SLUG)
        return (obj.data or {}).get("worktree_path") if obj else None
    finally:
        conn.close()


def test_y001_smoke_001_real_relocation_moves_git_and_store_together(tmp_path):
    root, legacy = _real_repo(tmp_path)
    destination = root / WORKTREE_ROOT / f"{PREFIX}-{SLUG}"

    returned = relocate_worktree(root, SLUG, destination)

    assert returned == destination
    assert destination.is_dir(), "the worktree is not at the destination"
    assert not legacy.exists(), "the worktree was left behind at the legacy path"

    # Uncommitted work survived the move — the whole reason worktrees are not
    # disposable state.
    assert (destination / "uncommitted.txt").read_text() == "work that must survive\n"

    # git agrees about where it now lives.
    listed = _git("worktree", "list", "--porcelain", cwd=root)
    registered = {
        Path(line.split(" ", 1)[1]).resolve()
        for line in listed.splitlines()
        if line.startswith("worktree ")
    }
    assert destination.resolve() in registered, (
        "git worktree list does not report the relocated path"
    )
    assert legacy.resolve() not in registered

    # And the store names the new path — no stale binding manufactured.
    assert _binding(root) == str(destination), (
        "the store binding still names the old path; relocation manufactured "
        "exactly the stale-binding class this issue exists to avoid"
    )
