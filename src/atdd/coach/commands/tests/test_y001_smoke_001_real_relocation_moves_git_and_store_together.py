# URN: test:place-worktrees:place-worktrees:Y001-SMOKE-001-real-relocation-moves-git-and-store-together
# Acceptance: acc:place-worktrees:Y001-SMOKE-001-real-relocation-moves-git-and-store-together
# WMBT: wmbt:place-worktrees:Y001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral

"""Y001-SMOKE-001 — real relocation moves git and the store together, and rolls
both back when the store write genuinely fails.

Two exercises over real machinery — a real `git worktree move`, a real State
Store write, real uncommitted work:

1. the happy path: git and the store move together and the work survives
   (Decision 3 on #1524 — a worktree can move itself);
2. the rollback: when the real store write fails, the git move is reversed so
   neither side is half-applied — the failure state the whole issue exists to
   avoid manufacturing.

FAULT INJECTION AT SMOKE LEVEL
------------------------------
Y001-UNIT-001 pins the rollback by SUBSTITUTING the store-write collaborator
(`monkeypatch.setattr`, with a call_count==1 proof-the-fault-landed guard).
A SMOKE test may not do that — `tester.smoke.no-collaborator-substitution`
forbids substituting a production collaborator, because that turns a smoke test
into a unit test wearing real-infrastructure clothes.

So the fault here is REAL, not substituted: the sqlite store is made genuinely
read-only, and the production `write_worktree_binding` fails against it exactly
as it would against a full disk or a revoked permission. The SMOKE-level
equivalent of the unit test's call_count guard is asserting the raised error is
`attempt to write a readonly database` — proof the failure occurred AT the
store-write seam, after the git move, rather than somewhere harmless earlier.
Without that, a relocation that failed before ever touching git would satisfy
every rollback assertion while exercising no rollback.
"""

from __future__ import annotations

import os
import sqlite3
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


def _store_path(root: Path) -> Path:
    """The real sqlite store file for this control root."""
    return Path(init_state_store(start=root))


def test_y001_smoke_001_real_store_write_failure_rolls_both_back(tmp_path):
    root, legacy = _real_repo(tmp_path)
    destination = root / WORKTREE_ROOT / f"{PREFIX}-{SLUG}"

    # Induce a REAL fault, not a substituted one: make the store read-only so
    # the production write_worktree_binding fails against real sqlite. The
    # directory is locked too, so sqlite cannot side-step via a fresh WAL file.
    store = _store_path(root)
    statedir = store.parent
    os.chmod(store, 0o444)
    os.chmod(statedir, 0o555)
    try:
        with pytest.raises(sqlite3.OperationalError) as exc:
            relocate_worktree(root, SLUG, destination)
    finally:
        # Restore write access so the rollback assertions can read the store.
        os.chmod(statedir, 0o755)
        os.chmod(store, 0o644)

    # Proof the fault landed AT the store-write seam (the SMOKE-level analogue of
    # the unit test's call_count==1). A readonly-database error can only come
    # from the write, which runs AFTER the git move — so the rollback below is
    # genuinely exercising the git-moved-then-store-failed path.
    assert "readonly database" in str(exc.value), (
        f"relocation failed with {exc.value!r}, not a store-write failure — "
        "the rollback assertions would be vacuous if git never moved"
    )

    # The rollback fired: the worktree is back at its original path, its work
    # intact, nothing left at the destination.
    assert legacy.exists(), "the worktree was not restored to its original path"
    assert (legacy / "uncommitted.txt").read_text() == "work that must survive\n", (
        "uncommitted work did not survive the rollback"
    )
    assert not destination.exists(), (
        f"the worktree was left at {destination} after the store write failed — "
        "git moved but the store did not, the exact half-applied state to avoid"
    )

    # git still reports the ORIGINAL path, and the store binding is unchanged.
    listed = _git("worktree", "list", "--porcelain", cwd=root)
    registered = {
        Path(line.split(" ", 1)[1]).resolve()
        for line in listed.splitlines()
        if line.startswith("worktree ")
    }
    assert legacy.resolve() in registered, (
        "git worktree list no longer reports the original path after rollback"
    )
    assert destination.resolve() not in registered
    assert _binding(root) == str(legacy), (
        "the store binding does not name the original path after rollback"
    )
