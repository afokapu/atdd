# URN: test:drive-state-machine:consolidate-store-writes:E004-UNIT-001-override-at-child-worktree-resolves-to-project-root
# Acceptance: acc:drive-state-machine:E004-UNIT-001-override-at-child-worktree-resolves-to-project-root
# WMBT: wmbt:drive-state-machine:E004
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: An ATDD_CONTROL_ROOT override pointing at a child worktree of a flat-sibling project resolves the store to the shared project root, not the worktree.
"""RED Test for test:drive-state-machine:consolidate-store-writes:E004-UNIT-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: RED
WMBT: wmbt:drive-state-machine:E004
Purpose: the interim ATDD_CONTROL_ROOT=<worktree> workaround must anchor at the
shared project-root store instead of forking a per-worktree one.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state.paths import LayoutMode, resolve_control_root


def _mk_worktree(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    (path / ".atdd").mkdir(parents=True, exist_ok=True)
    (path / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")
    return path


def test_override_at_child_worktree_resolves_to_project_root(tmp_path):
    project = tmp_path / "project"
    main = _mk_worktree(project / "main")
    wt = _mk_worktree(project / "wt1")
    gcd = lambda _start: main / ".git"  # flat-sibling common dir

    res = resolve_control_root(
        wt, env={"ATDD_CONTROL_ROOT": str(wt)}, git_common_dir=gcd
    )

    assert res.control_root == project
    assert res.layout_mode is LayoutMode.SIBLING_WORKTREE
    assert res.state_store_path == project / ".atdd" / "state" / "state.sqlite"
