# URN: test:drive-state-machine:consolidate-store-writes:E006-UNIT-002-control-root-extension-wins-runtime-left-scratch
# Acceptance: acc:drive-state-machine:E006-UNIT-002-control-root-extension-wins-on-conflict-runtime-left-scratch
# WMBT: wmbt:drive-state-machine:E006
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: On an id+version already present at the control root the control-root copy wins (no overwrite); scratch dirs (runtime) are left untouched.
"""RED Test for test:drive-state-machine:consolidate-store-writes:E006-UNIT-002.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: RED
WMBT: wmbt:drive-state-machine:E006
Purpose: consolidation never overwrites an existing control-root install and
leaves scratch (.atdd/runtime/) per-worktree per #1179.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state.cli import migrate_layout
from atdd.state.db import connect, init_state_store


def test_control_root_extension_wins_and_runtime_left_scratch(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    croot = project / ".atdd"
    connect(init_state_store(db_path=croot / "state" / "state.sqlite")).close()
    # control root ALREADY has the extension installed (authoritative)
    cr_home = croot / "extensions" / "atdd.extension.demo" / "0.1.0"
    cr_home.mkdir(parents=True)
    (cr_home / "marker").write_text("control-root\n")

    wt = project / "wt1"
    (wt / ".git").mkdir(parents=True)
    # worktree has the SAME id+version (redundant reinstall) with a different marker
    wt_home = wt / ".atdd" / "extensions" / "atdd.extension.demo" / "0.1.0"
    wt_home.mkdir(parents=True)
    (wt_home / "marker").write_text("from-worktree\n")
    # plus a scratch runtime dir that must be left alone
    (wt / ".atdd" / "runtime" / "agents").mkdir(parents=True)
    (wt / ".atdd" / "runtime" / "agents" / "x.json").write_text("{}\n")

    migrate_layout(project_root=project)

    # control-root copy preserved (no overwrite from the worktree)
    assert (cr_home / "marker").read_text() == "control-root\n"
    # per-worktree extension removed
    assert not (wt / ".atdd" / "extensions").exists()
    # scratch runtime left untouched
    assert (wt / ".atdd" / "runtime" / "agents" / "x.json").is_file()
