# URN: test:place-worktrees:place-worktrees:Y001-UNIT-003-relocation-is-reachable-from-the-cli
# Acceptance: acc:place-worktrees:Y001-UNIT-003-relocation-is-reachable-from-the-cli
# WMBT: wmbt:place-worktrees:Y001
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""Y001-UNIT-003 — the relocation machinery has an entry point.

Issue #1524 scopes "self-relocation: ... offer to `git worktree move` the current
worktree under the configured root, with a transactional State Store fixup". The
transactional move shipped and was pinned by Y001-UNIT-001, Y001-UNIT-002 and
Y001-SMOKE-001 — and nothing called it. `relocate_worktree` and
`relocation_offer` appeared in the source exactly twice each: their definition,
and their own tests.

That is the failure mode this acceptance exists for. Three green acceptances
around a function no command invokes prove the function works; they do not prove
the issue's outcome, because an operator has no way to reach it. The other three
pin that relocation is CORRECT. This one pins that it is REACHABLE.

Phase GREEN: `atdd worktree relocate` resolves the offer, reports it, moves on
--apply, and declines by reason for an unbound worktree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.coach]

SLUG = "config-driven-worktree-placement"
PREFIX = "feat"


def _git(*args: str, cwd: Path) -> None:
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"


def _repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A real repo with one BOUND legacy worktree and one unbound one."""
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
        "worktree_root: worktrees\n"
    )

    # At the LEGACY flat-sibling location, which is what draining looks like.
    bound = root.parent / f"{PREFIX}-{SLUG}"
    _git("worktree", "add", "-q", "-b", f"{PREFIX}/{SLUG}", str(bound), cwd=root)
    (bound / "wip.txt").write_text("uncommitted\n")

    unbound = root.parent / "cw-phase0"
    _git("worktree", "add", "-q", "-b", "cw/phase0", str(unbound), cwd=root)

    conn = connect(init_state_store(start=root))
    try:
        StateStore(conn).objects.upsert(
            SLUG,
            WORK_ITEM_KIND,
            state="RED",
            data={"branch": f"{PREFIX}/{SLUG}", "worktree_path": str(bound)},
        )
        conn.commit()
    finally:
        conn.close()
    return root, bound, unbound


def _binding(root: Path, slug: str) -> str:
    conn = connect(init_state_store(start=root))
    try:
        return (StateStore(conn).objects.get(slug).data or {}).get("worktree_path")
    finally:
        conn.close()


def test_y001_unit_003_relocation_is_reachable_from_the_cli(tmp_path, capsys):
    from atdd.coach.commands.worktree_relocate import run_relocate

    root, bound, unbound = _repo(tmp_path)
    destination = root.parent / "worktrees" / f"{PREFIX}-{SLUG}"

    # -- dry run: reports both ends, moves nothing -------------------------
    assert run_relocate(target=str(bound)) == 0
    out = capsys.readouterr().out
    assert str(bound) in out and str(destination) in out
    assert bound.is_dir(), "a dry run moved the worktree"
    assert not destination.exists()
    assert _binding(root, SLUG) == str(bound), "a dry run rewrote the binding"

    # -- apply: git and the store move together ---------------------------
    assert run_relocate(target=str(bound), apply=True) == 0
    assert destination.is_dir() and not bound.exists()
    assert (destination / "wip.txt").read_text() == "uncommitted\n", (
        "relocation lost uncommitted work"
    )
    assert _binding(root, SLUG) == str(destination), (
        "the move happened but the store still names the old path — the "
        "stale-binding class this issue exists not to manufacture"
    )

    registered = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(root), capture_output=True, text=True,
    ).stdout
    assert str(destination) in registered and str(bound) not in registered

    # -- declining is not failing ------------------------------------------
    capsys.readouterr()
    assert run_relocate(target=str(unbound)) == 0, (
        "an unbound worktree is a correct outcome, not an error: exiting "
        "non-zero would fail any script that relocates opportunistically"
    )
    declined = capsys.readouterr().out
    assert "unbound" in declined or "no work item" in declined
    assert unbound.is_dir(), "an unbound worktree was moved on a guess"

    # Already-placed is likewise a decline, not an error or a second move.
    assert run_relocate(target=str(destination), apply=True) == 0
    assert destination.is_dir()
