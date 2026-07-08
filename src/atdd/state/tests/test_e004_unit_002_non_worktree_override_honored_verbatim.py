# URN: test:drive-state-machine:consolidate-store-writes:E004-UNIT-002-non-worktree-override-honored-verbatim
# Acceptance: acc:drive-state-machine:E004-UNIT-002-non-worktree-override-honored-verbatim
# WMBT: wmbt:drive-state-machine:E004
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: An override that is NOT a flat-sibling child worktree (hermetic tmp / single-repo / consumer repo) is honored verbatim — no behavior change for isolated tests and consumer installs.
"""RED Test for test:drive-state-machine:consolidate-store-writes:E004-UNIT-002.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: RED
WMBT: wmbt:drive-state-machine:E004
Purpose: the override-redirect must be surgical — it only fires for a child
worktree of a flat-sibling project; every other override is taken verbatim.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state.paths import LayoutMode, resolve_control_root


def _mk_worktree(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    (path / ".atdd" / "state").mkdir(parents=True, exist_ok=True)
    return path


def test_hermetic_override_without_git_is_honored_verbatim(tmp_path):
    # git unavailable / not a flat-sibling layout -> override taken as-is.
    isolated = _mk_worktree(tmp_path / "isolated")

    res = resolve_control_root(
        isolated, env={"ATDD_CONTROL_ROOT": str(isolated)},
        git_common_dir=lambda _s: None,
    )

    assert res.control_root == isolated


def test_single_repo_override_is_honored_verbatim(tmp_path):
    # A single-repo checkout: its own git root == override. Not flat-sibling,
    # so the store stays inside the repo (today's behavior, unchanged).
    repo = _mk_worktree(tmp_path / "repo")

    res = resolve_control_root(
        repo, env={"ATDD_CONTROL_ROOT": str(repo)},
        git_common_dir=lambda _s: repo / ".git",
    )

    assert res.control_root == repo
    assert res.layout_mode is LayoutMode.SINGLE_REPO
