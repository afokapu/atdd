# URN: test:drive-state-machine:consolidate-store-writes:M003-UNIT-001-guard-flags-per-worktree-extensions-not-scratch
# Acceptance: acc:drive-state-machine:M003-UNIT-001-guard-flags-per-worktree-extensions-not-scratch
# WMBT: wmbt:drive-state-machine:M003
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: check_layout flags a per-worktree .atdd/extensions/ below the control root (generalized beyond the store) but ignores a scratch-only .atdd/runtime/.
"""RED Test for test:drive-state-machine:consolidate-store-writes:M003-UNIT-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: RED
WMBT: wmbt:drive-state-machine:M003
Purpose: the single-store guard is generalized to any operational .atdd/ subtree
(store OR extensions/workspaces), while scratch (runtime/cache/diagnostics) is
still ignored per #1179.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state.paths import check_layout


def _mk_worktree(path: Path) -> Path:
    (path / ".git").mkdir(parents=True, exist_ok=True)
    (path / ".atdd").mkdir(parents=True, exist_ok=True)
    return path


def test_guard_flags_per_worktree_extensions_not_scratch(tmp_path):
    project = tmp_path / "project"
    (project / ".atdd").mkdir(parents=True)

    # wt1: a rogue per-worktree extension install (no store)
    wt1 = _mk_worktree(project / "wt1")
    (wt1 / ".atdd" / "extensions" / "atdd.extension.demo" / "0.1.0").mkdir(parents=True)

    # wt2: only a scratch runtime dir (must NOT be flagged)
    wt2 = _mk_worktree(project / "wt2")
    (wt2 / ".atdd" / "runtime" / "agents").mkdir(parents=True)

    violations = check_layout(project)
    blob = "\n".join(violations)

    # the rogue extensions subtree is flagged and named
    assert any("extensions" in v and "wt1" in v for v in violations), blob
    # the scratch runtime dir is not flagged
    assert "wt2" not in blob
