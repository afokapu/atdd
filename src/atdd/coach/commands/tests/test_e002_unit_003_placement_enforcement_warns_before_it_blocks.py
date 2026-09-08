# URN: test:place-worktrees:place-worktrees:E002-UNIT-003-placement-enforcement-warns-before-it-blocks
# Acceptance: acc:place-worktrees:E002-UNIT-003-placement-enforcement-warns-before-it-blocks
# WMBT: wmbt:place-worktrees:E002
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""E002-UNIT-003 — enforcement warns for a release before it blocks.

Issue #1524, Decision 4: enforce placement via a git hook, "warn for one release
then block", because "blocking on day one walls an agent off after it has done
its work".

The staging is a CONFIG key, not a date or a version comparison. A time bomb
would flip on its own in a repo whose worktrees had not finished draining, which
is walling an agent off mid-flow on a schedule nobody was watching — the same
failure, arriving later and with less warning.

So the default matters more than the block does, and most of this test is about
what the gate refuses to refuse.
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


def _write_config(root: Path, *, enforcement: str | None) -> None:
    config = "version: '1.0'\nworktree_root: worktrees\n"
    if enforcement is not None:
        config += f"worktree_placement_enforcement: {enforcement}\n"
    (root / ".atdd" / "config.yaml").write_text(config)


def _repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "main"
    root.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)
    _git("config", "user.name", "Test", cwd=root)
    (root / "README.md").write_text("seed\n")
    _git("add", "README.md", cwd=root)
    _git("commit", "-q", "-m", "seed", cwd=root)
    (root / ".atdd").mkdir()
    _write_config(root, enforcement=None)

    drifted = root.parent / "feat-drifted"
    _git("worktree", "add", "-q", "-b", "feat/drifted", str(drifted), cwd=root)

    unbound = root.parent / "cw-phase0"
    _git("worktree", "add", "-q", "-b", "cw/phase0", str(unbound), cwd=root)

    conn = connect(init_state_store(start=root))
    try:
        StateStore(conn).objects.upsert(
            "drifted", WORK_ITEM_KIND, state="RED",
            data={"branch": "feat/drifted", "worktree_path": str(drifted)},
        )
        conn.commit()
    finally:
        conn.close()
    return root, drifted, unbound


def test_e002_unit_003_placement_enforcement_warns_before_it_blocks(tmp_path):
    from atdd.coach.commands.worktree_placement_enforcement import (
        placement_block_reason,
        resolve_enforcement,
    )

    root, drifted, unbound = _repo(tmp_path)

    # -- the default release: reports, refuses nothing -----------------------
    assert resolve_enforcement(root) == "warn", (
        "the default stage must be warn — a repo that upgrades into this "
        "feature must not start refusing pushes"
    )
    assert placement_block_reason(drifted) is None, (
        "a misplaced worktree was BLOCKED at the warn stage, which is exactly "
        "the day-one walling-off Decision 4 stages to avoid"
    )

    _write_config(root, enforcement="warn")
    assert placement_block_reason(drifted) is None

    _write_config(root, enforcement="off")
    assert placement_block_reason(drifted) is None

    # -- opted in: blocks, and says how to clear the block -------------------
    _write_config(root, enforcement="block")
    reason = placement_block_reason(drifted)
    assert reason, "the block stage did not block a misplaced, bound worktree"
    assert str(drifted) in reason
    assert str(root.parent / "worktrees" / "feat-drifted") in reason
    assert "atdd worktree relocate" in reason, (
        "the gate refuses a push without naming the command that clears it — "
        "an enforcement an operator cannot act on teaches them to bypass"
    )

    # -- silent even at block, for anything not unambiguously fixable --------
    assert placement_block_reason(unbound) is None, (
        "a push was refused for an unbound worktree, which cannot be relocated "
        "without guessing — so the operator has no way to clear the block"
    )
    assert placement_block_reason(root) is None, (
        "a push from the primary checkout was refused; it is the anchor, not a "
        "worktree, and it is never relocated"
    )

    placed = root.parent / "worktrees" / "feat-placed"
    placed.parent.mkdir(parents=True, exist_ok=True)
    _git("worktree", "add", "-q", "-b", "feat/placed", str(placed), cwd=root)
    conn = connect(init_state_store(start=root))
    try:
        StateStore(conn).objects.upsert(
            "placed", WORK_ITEM_KIND, state="RED",
            data={"branch": "feat/placed", "worktree_path": str(placed)},
        )
        conn.commit()
    finally:
        conn.close()
    assert placement_block_reason(placed) is None

    # -- a typo reads as the default, it does not raise at push time --------
    _write_config(root, enforcement="blokc")
    assert resolve_enforcement(root) == "warn", (
        "an unrecognised value must read as the default; a hook is the worst "
        "place to discover a typo in a config key"
    )
    assert placement_block_reason(drifted) is None
