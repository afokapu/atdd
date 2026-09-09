# URN: test:place-worktrees:place-worktrees:Y001-UNIT-004-version-change-surfaces-the-relocation-offer
# Acceptance: acc:place-worktrees:Y001-UNIT-004-version-change-surfaces-the-relocation-offer
# WMBT: wmbt:place-worktrees:Y001
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""Y001-UNIT-004 — the relocation offer is actually surfaced, and only surfaced.

Issue #1524 scopes self-relocation as happening "on the first `atdd` command
after a version change": detect layout drift, then offer the move. Y001-UNIT-003
pins that the move is reachable when someone goes looking for it; this one pins
that they are TOLD to look.

The four silent cases matter as much as the loud one. This check hangs off
`print_upgrade_sync_notice`, which runs on every CLI invocation under an
explicitly read-only contract (#342: a banner that also wrote to the working
tree was the bug that contract exists to prevent). So the notice must stay
silent for the primary checkout, for an unbound worktree it cannot place
without guessing, for a worktree already where it belongs, and for a repo that
never configured placement — and it must never move, write, prompt, or raise.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.coach]


def _git(*args: str, cwd: Path) -> None:
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"


def _bind(root: Path, slug: str, branch: str, path: Path) -> None:
    conn = connect(init_state_store(start=root))
    try:
        StateStore(conn).objects.upsert(
            slug, WORK_ITEM_KIND, state="RED",
            data={"branch": branch, "worktree_path": str(path)},
        )
        conn.commit()
    finally:
        conn.close()


def _repo(tmp_path: Path, *, worktree_root: str | None) -> Path:
    root = tmp_path / "main"
    root.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)
    _git("config", "user.name", "Test", cwd=root)
    (root / "README.md").write_text("seed\n")
    _git("add", "README.md", cwd=root)
    _git("commit", "-q", "-m", "seed", cwd=root)
    (root / ".atdd").mkdir()
    config = "version: '1.0'\n"
    if worktree_root is not None:
        config += f"worktree_root: {worktree_root}\n"
    (root / ".atdd" / "config.yaml").write_text(config)
    return root


def test_y001_unit_004_version_change_surfaces_the_relocation_offer(tmp_path):
    from atdd.coach.commands.worktree_placement import placement_drift_notice

    root = _repo(tmp_path / "configured", worktree_root="worktrees")

    # -- the one loud case: bound, and in the wrong place --------------------
    drifted = root.parent / "feat-drifted"
    _git("worktree", "add", "-q", "-b", "feat/drifted", str(drifted), cwd=root)
    _bind(root, "drifted", "feat/drifted", drifted)

    notice = placement_drift_notice(drifted)
    assert notice, "a bound, misplaced worktree got no relocation offer at all"
    assert str(drifted) in notice, "the notice does not say where the worktree is"
    assert str(root.parent / "worktrees" / "feat-drifted") in notice, (
        "the notice does not say where it belongs"
    )
    assert "atdd worktree relocate" in notice, (
        "the notice names a problem without naming the command that fixes it"
    )
    # Reporting only: the offer must not have acted on itself.
    assert drifted.is_dir(), "the drift NOTICE moved the worktree"
    assert not (root.parent / "worktrees").exists()

    # -- silent: already where the config says ------------------------------
    placed = root.parent / "worktrees" / "feat-placed"
    placed.parent.mkdir(parents=True, exist_ok=True)
    _git("worktree", "add", "-q", "-b", "feat/placed", str(placed), cwd=root)
    _bind(root, "placed", "feat/placed", placed)
    assert placement_drift_notice(placed) is None

    # -- silent: unbound, because placing it would be a guess ---------------
    unbound = root.parent / "cw-phase0"
    _git("worktree", "add", "-q", "-b", "cw/phase0", str(unbound), cwd=root)
    assert placement_drift_notice(unbound) is None, (
        "an unbound worktree was offered a destination the store cannot justify"
    )

    # -- silent: the primary checkout is the anchor, not a worktree ---------
    assert placement_drift_notice(root) is None, (
        "the primary checkout was offered relocation — moving it would move "
        "the very directory the project root is derived from"
    )

    # -- silent: a repo that never configured placement ---------------------
    plain = _repo(tmp_path / "plain", worktree_root=None)
    plain_wt = plain.parent / "feat-plain"
    _git("worktree", "add", "-q", "-b", "feat/plain", str(plain_wt), cwd=plain)
    _bind(plain, "plain", "feat/plain", plain_wt)
    assert placement_drift_notice(plain_wt) is None, (
        "an unconfigured repo was told its layout had drifted — forward-only "
        "means configuring nothing changes nothing, including the messaging"
    )


def test_y001_unit_004_notice_never_raises(tmp_path):
    """Any failure at all is swallowed: this runs on every upgraded CLI call."""
    from atdd.coach.commands.worktree_placement import placement_drift_notice

    # Not a git repo, and not even a directory that exists.
    assert placement_drift_notice(tmp_path / "nowhere") is None
    assert placement_drift_notice(tmp_path) is None
