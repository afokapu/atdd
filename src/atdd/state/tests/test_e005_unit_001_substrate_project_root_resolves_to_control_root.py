# URN: test:drive-state-machine:consolidate-store-writes:E005-UNIT-001-substrate-project-root-resolves-to-control-root
# Acceptance: acc:drive-state-machine:E005-UNIT-001-substrate-project-root-resolves-to-control-root
# WMBT: wmbt:drive-state-machine:E005
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: The substrate CLI resolves its project_root to the control root, so an install from a child worktree targets the control-root .atdd/ rather than the worktree.
"""RED Test for test:drive-state-machine:consolidate-store-writes:E005-UNIT-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: RED
WMBT: wmbt:drive-state-machine:E005
Purpose: extension installs must resolve to the single control-root .atdd/ — the
substrate operational-root resolver returns the control root for a child
worktree, and falls back to the given root when resolution is not possible.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state.paths import resolve_operational_root


def _mk_worktree(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    (path / ".atdd").mkdir(parents=True, exist_ok=True)
    (path / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")
    return path


def test_substrate_root_resolves_to_control_root_from_worktree(tmp_path):
    project = tmp_path / "project"
    main = _mk_worktree(project / "main")
    wt = _mk_worktree(project / "wt1")
    gcd = lambda _s: main / ".git"

    root = resolve_operational_root(wt, env={}, git_common_dir=gcd)

    assert root == project  # control root, not wt1


def test_substrate_root_falls_back_to_start_when_no_control_root(tmp_path):
    # A bare directory with no .atdd/ and no git: resolution is impossible, so the
    # given root is honored (consumer repo / first-run install is unchanged).
    consumer = tmp_path / "consumer"
    consumer.mkdir()

    root = resolve_operational_root(consumer, env={}, git_common_dir=lambda _s: None)

    assert root == consumer
