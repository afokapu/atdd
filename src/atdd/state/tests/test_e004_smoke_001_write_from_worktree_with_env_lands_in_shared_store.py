# URN: test:drive-state-machine:consolidate-store-writes:E004-SMOKE-001-write-from-worktree-with-env-lands-in-shared-store
# Acceptance: acc:drive-state-machine:E004-SMOKE-001-write-from-worktree-with-env-lands-in-shared-store
# WMBT: wmbt:drive-state-machine:E004
# Phase: SMOKE
# Runtime: python
# Layer: integration
# Assertion: behavioral
# Purpose: With the interim ATDD_CONTROL_ROOT=<worktree> set in a real flat-sibling project, a hot-path store write lands in the single shared control-root store, not a new per-worktree store.
"""SMOKE Test for test:drive-state-machine:consolidate-store-writes:E004-SMOKE-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: SMOKE
WMBT: wmbt:drive-state-machine:E004
Purpose: exercise the real git-backed resolver end-to-end — a write issued from a
worktree while the interim env workaround is set must not fork a per-worktree DB.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from atdd.state.db import connect, init_state_store

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git required for the live worktree smoke")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def test_write_from_worktree_with_env_lands_in_shared_store(tmp_path, monkeypatch):
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

    # the documented interim workaround: env pinned to the child worktree
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(wt1))

    # a hot-path write opening the store from within the worktree
    db_path = init_state_store(start=wt1)
    connect(db_path).close()

    shared = project / ".atdd" / "state" / "state.sqlite"
    assert db_path.resolve() == shared.resolve()
    # no rogue per-worktree store was created by the write
    assert not (wt1 / ".atdd" / "state" / "state.sqlite").exists()
