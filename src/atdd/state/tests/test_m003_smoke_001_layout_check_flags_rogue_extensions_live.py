# URN: test:drive-state-machine:consolidate-store-writes:M003-SMOKE-001-layout-check-flags-rogue-extensions-live
# Acceptance: acc:drive-state-machine:M003-SMOKE-001-layout-check-flags-rogue-extensions-live
# WMBT: wmbt:drive-state-machine:M003
# Phase: SMOKE
# Runtime: python
# Layer: integration
# Assertion: behavioral
# Purpose: Against real runtime, layout --check exits non-zero when a worktree carries a rogue .atdd/extensions/ install below the control root, and clears once removed.
"""SMOKE Test for test:drive-state-machine:consolidate-store-writes:M003-SMOKE-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: SMOKE
WMBT: wmbt:drive-state-machine:M003
Purpose: exercise the generalized guard over a real git worktree layout — a rogue
per-worktree extension install makes `atdd state layout --check` fail; removing it
clears the check.
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
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def test_layout_check_flags_rogue_extensions_live(tmp_path):
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

    # single consolidated control-root store: clean
    connect(init_state_store(start=main)).close()
    assert state_cli.run(["layout", "--check", "--root", str(wt1)]) == 0

    # a rogue per-worktree extension install appears
    rogue = wt1 / ".atdd" / "extensions" / "atdd.extension.demo" / "0.1.0"
    rogue.mkdir(parents=True)
    (rogue / "marker").write_text("x\n")
    assert state_cli.run(["layout", "--check", "--root", str(wt1)]) != 0

    # removing it clears the check
    shutil.rmtree(wt1 / ".atdd" / "extensions")
    assert state_cli.run(["layout", "--check", "--root", str(wt1)]) == 0
