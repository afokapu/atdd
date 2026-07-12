# URN: test:drive-state-machine:consolidate-store-writes:M002-SMOKE-001-doctor-flags-and-clears-rogue-store
# Acceptance: acc:drive-state-machine:M002-SMOKE-001-doctor-flags-and-clears-rogue-store
# WMBT: wmbt:drive-state-machine:M002
# Phase: SMOKE
# Runtime: python
# Layer: integration
# Assertion: behavioral
# Purpose: Against real runtime, layout --check flags a rogue per-worktree store with a non-zero exit and reports OK only after it is removed.
"""SMOKE Test for test:drive-state-machine:consolidate-store-writes:M002-SMOKE-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: SMOKE
WMBT: wmbt:drive-state-machine:M002
Purpose: exercise the guard over a real git worktree layout — a rogue store makes
`atdd state layout --check` fail; removing it clears the check.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from atdd.state import cli as state_cli
from atdd.state.db import connect, init_state_store

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git required for the live worktree smoke")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def test_doctor_flags_and_clears_rogue_store(tmp_path):
    project = tmp_path / "project"
    main = project / "main"
    main.mkdir(parents=True)
    _git(main, "init", "-q")
    _git(main, "config", "user.email", "t@t.t")
    _git(main, "config", "user.name", "t")
    (main / "f.txt").write_text("x\n")
    _git(main, "add", "-A")
    _git(main, "commit", "-qm", "init")
    wt1 = project / "wt1"
    _git(main, "worktree", "add", "-q", str(wt1), "-b", "wt1")

    # a single consolidated control-root store: layout --check is clean
    connect(init_state_store(start=main)).close()
    assert state_cli.run(["layout", "--check", "--root", str(wt1)]) == 0

    # regression: a rogue per-worktree store appears
    rogue = wt1 / ".atdd" / "state" / "state.sqlite"
    rogue.parent.mkdir(parents=True, exist_ok=True)
    rogue.touch()
    assert state_cli.run(["layout", "--check", "--root", str(wt1)]) != 0

    # removing it clears the check again
    rogue.unlink()
    assert state_cli.run(["layout", "--check", "--root", str(wt1)]) == 0
