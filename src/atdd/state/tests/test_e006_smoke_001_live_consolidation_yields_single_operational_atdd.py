# URN: test:drive-state-machine:consolidate-store-writes:E006-SMOKE-001-live-consolidation-yields-single-operational-atdd
# Acceptance: acc:drive-state-machine:E006-SMOKE-001-live-consolidation-yields-single-operational-atdd
# WMBT: wmbt:drive-state-machine:E006
# Phase: SMOKE
# Runtime: python
# Layer: integration
# Assertion: behavioral
# Purpose: Against a real multi-worktree project, consolidation collapses store AND extension installs into one control-root .atdd/.
"""SMOKE Test for test:drive-state-machine:consolidate-store-writes:E006-SMOKE-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: SMOKE
WMBT: wmbt:drive-state-machine:E006
Purpose: exercise the generalized consolidation over a real git worktree layout —
store AND extensions fold into one control-root .atdd/, per-worktree copies gone,
layout --check clean.
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


def test_live_consolidation_yields_single_operational_atdd(tmp_path):
    project = tmp_path / "project"
    main = project / "main"
    main.mkdir(parents=True)
    _git(main, "init", "-q")
    _git(main, "config", "user.email", "t@t.t")
    _git(main, "config", "user.name", "t")
    (main / ".atdd").mkdir()
    (main / ".atdd" / "config.yaml").write_text("x\n")
    (main / "f.txt").write_text("x\n")
    _git(main, "add", "-A")
    _git(main, "commit", "-qm", "init")
    wt1 = project / "wt1"
    _git(main, "worktree", "add", "-q", str(wt1), "-b", "wt1")

    # worktree carries its own store AND its own extension install
    connect(init_state_store(db_path=wt1 / ".atdd" / "state" / "state.sqlite")).close()
    ext = wt1 / ".atdd" / "extensions" / "atdd.extension.demo" / "0.1.0"
    ext.mkdir(parents=True)
    (ext / "marker").write_text("x\n")

    assert state_cli.run(["layout", "--check", "--root", str(wt1)]) != 0

    rc = state_cli.run(["migrate-layout", "--project-root", str(project)])
    assert rc == 0

    croot = project / ".atdd"
    assert (croot / "state" / "state.sqlite").is_file()
    assert (croot / "extensions" / "atdd.extension.demo" / "0.1.0" / "marker").is_file()
    assert not (wt1 / ".atdd" / "state" / "state.sqlite").exists()
    assert not (wt1 / ".atdd" / "extensions").exists()
    assert state_cli.run(["layout", "--check", "--root", str(wt1)]) == 0
