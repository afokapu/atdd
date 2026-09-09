# URN: test:place-worktrees:place-worktrees:Y001-UNIT-001-failed-store-write-rolls-back-the-move
# Acceptance: acc:place-worktrees:Y001-UNIT-001-failed-store-write-rolls-back-the-move
# WMBT: wmbt:place-worktrees:Y001
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""Y001-UNIT-001 — a failed store write rolls the relocation back.

Issue #1524, Notes: relocation must `git worktree move` the directory AND rewrite
the absolute `data.worktree_path` in the State Store blob. If git moves and the
store write fails, the store points at a directory that no longer exists — which
is exactly the stale-binding class this repo already carries 31 of. That is the
one genuinely painful failure state, so it is pinned before the happy path.

FAULT INJECTION — why this test cannot fail open
------------------------------------------------
A fault-injection test that never injects passes green while testing nothing. The
usual defence for SOURCE-MUTATING injection is "anchor matched exactly once, then
ast.parse the result" — proving the edit landed and left valid Python. This test
mutates no source: it injects at the store-write seam via patching, so there is
no text anchor to count and nothing to re-parse.

The equivalent proof obligation still holds and is discharged explicitly below:
the injected failure must have been REACHED exactly once. Without that assertion,
a relocation that returned early — never attempting the store write at all —
would satisfy every rollback assertion here while exercising no rollback.

Phase RED: fails on the import — the relocation seam does not exist.
Phase GREEN: git move and store write commit or roll back together.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.coach]

ISSUE = 1524
SLUG = "config-driven-worktree-placement"
PREFIX = "feat"


class _InjectedStoreFailure(RuntimeError):
    """The fault this test injects at the store-write seam."""


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    """A control root plus a bound worktree at the legacy sibling location."""
    root = tmp_path / "main"
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\n"
        "github:\n"
        "  repo: owner/repo\n"
        "  default_branch: main\n"
        "worktree_root: worktrees\n"
    )
    origin = root.parent / f"{PREFIX}-{SLUG}"
    origin.mkdir(parents=True)
    (origin / "uncommitted.txt").write_text("work that must survive\n")

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
                "worktree_path": str(origin),
            },
        )
        store.external_refs.link(SLUG, GITHUB_PROVIDER, "issue", str(ISSUE))
        conn.commit()
    finally:
        conn.close()
    return root, origin


def _binding(root: Path) -> str | None:
    conn = connect(init_state_store(start=root))
    try:
        obj = StateStore(conn).objects.get(SLUG)
        return (obj.data or {}).get("worktree_path") if obj else None
    finally:
        conn.close()


def test_y001_unit_001_failed_store_write_rolls_back_the_move(tmp_path, monkeypatch):
    from atdd.coach.commands.worktree_placement import relocate_worktree

    root, origin = _repo(tmp_path)
    destination = root / "worktrees" / f"{PREFIX}-{SLUG}"

    # --- inject the fault at the store-write seam ------------------------
    injected = MagicMock(side_effect=_InjectedStoreFailure("injected store write failure"))
    monkeypatch.setattr(
        "atdd.coach.commands.worktree_placement.write_worktree_binding", injected
    )

    with pytest.raises(_InjectedStoreFailure):
        relocate_worktree(root, SLUG, destination)

    # --- PROOF THE FAULT LANDED (see module docstring) -------------------
    # Exactly once: zero means the relocation never attempted the store write
    # and the rollback assertions below would be vacuous; more than once means
    # it retried, and "rolled back" would be ambiguous about which attempt.
    assert injected.call_count == 1, (
        f"injected store-write fault was reached {injected.call_count} times, "
        "expected exactly 1 — the rollback assertions below only mean "
        "something if the write was genuinely attempted and genuinely failed"
    )

    # --- the acceptance: neither side is half-applied --------------------
    assert origin.exists(), "the worktree was not restored to its original path"
    assert (origin / "uncommitted.txt").read_text() == "work that must survive\n", (
        "uncommitted work did not survive the rollback"
    )
    assert not destination.exists(), (
        f"the worktree was left at the destination {destination} after the "
        "store write failed — git moved but the store did not"
    )
    assert _binding(root) == str(origin), (
        "the store binding does not name the original path after rollback — "
        "this is the stale-binding class the issue exists to avoid creating"
    )
