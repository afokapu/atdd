# URN: test:govern-lifecycle:keep-local-main-current-branch-from-origin:E010-UNIT-001-branch-manager-cuts-from-origin-default
# Acceptance: acc:govern-lifecycle:E010-UNIT-001-branch-manager-cuts-from-origin-default
# WMBT: wmbt:govern-lifecycle:E010
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""E010-UNIT-001 — BranchManager.branch() passes origin/<default_branch> as
the start-point to git worktree add, and does a targeted fetch of
origin/<default_branch> before creating the worktree.

Phase RED: fails because branch.py passes no start-point to git worktree add.
Phase GREEN: git worktree add receives 'origin/main' as its final argument.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import yaml

from atdd.coach.commands.branch import BranchManager

pytestmark = [pytest.mark.coach]


def _proc(returncode: int = 0, stdout: str = "", stderr: str = ""):
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def _make_manifest(tmp_path: Path, issue_number: int = 1, slug: str = "my-feature") -> None:
    manifest = {
        "sessions": [
            {"issue_number": issue_number, "slug": slug, "type": "implementation"}
        ]
    }
    (tmp_path / ".atdd").mkdir(exist_ok=True)
    (tmp_path / ".atdd" / "manifest.yaml").write_text(yaml.dump(manifest))
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "github:\n  repo: owner/repo\n  default_branch: main\n"
    )


def _run_factory(calls: list, remote_branch_exists: bool = False):
    """Return a subprocess.run side_effect that records worktree add invocations."""

    def side_effect(cmd, **kwargs):
        calls.append(list(cmd))
        # git fetch origin <default_branch> — success
        if cmd[:2] == ["git", "fetch"]:
            return _proc(0)
        # git branch -r --list — no remote branch (so new branch path)
        if cmd[:3] == ["git", "branch", "-r"]:
            stdout = f"  origin/feat/my-feature" if remote_branch_exists else ""
            return _proc(0, stdout)
        # git worktree add — success
        if cmd[:3] == ["git", "worktree", "add"]:
            return _proc(0)
        # git push -u origin — success
        if cmd[:2] == ["git", "push"]:
            return _proc(0, "", "")
        # gh pr list — no existing PR
        if cmd[:3] == ["gh", "pr", "list"]:
            return _proc(0, "", "")
        # git rev-list --count (empty-branch check)
        if cmd[:3] == ["git", "rev-list", "--count"]:
            return _proc(0, "0", "")
        return _proc(0)

    return side_effect


def test_worktree_add_receives_origin_default_as_start_point(tmp_path, capsys):
    """git worktree add must include 'origin/main' as the start-point."""
    _make_manifest(tmp_path, issue_number=1, slug="my-feature")
    recorded: list = []

    with patch(
        "atdd.coach.commands.branch.subprocess.run",
        side_effect=_run_factory(recorded),
    ), patch(
        "atdd.coach.commands.branch.resolve_default_branch",
        return_value="main",
    ), patch(
        "atdd.coach.utils.repo.detect_worktree_layout",
        return_value="worktree-ready",
    ), patch(
        "atdd.coach.commands.initializer.write_workspace",
        return_value=None,
    ), patch(
        "atdd.coach.commands.branch.ProjectConfig",
    ), patch(
        "atdd.coach.commands.branch.GitHubClient",
    ):
        mgr = BranchManager(target_dir=tmp_path)
        mgr.branch(issue_number=1)

    worktree_add_calls = [c for c in recorded if c[:3] == ["git", "worktree", "add"]]
    assert worktree_add_calls, "No git worktree add call recorded"

    wt_cmd = worktree_add_calls[0]
    assert "origin/main" in wt_cmd, (
        f"Expected 'origin/main' start-point in git worktree add, got: {wt_cmd}"
    )
    assert "-b" in wt_cmd, "Expected '-b' flag in git worktree add"


def test_fetch_is_targeted_to_default_branch(tmp_path):
    """git fetch must be a targeted fetch of origin <default_branch>, not 'git fetch origin' (all)."""
    _make_manifest(tmp_path, issue_number=2, slug="targeted-fetch")
    recorded: list = []

    with patch(
        "atdd.coach.commands.branch.subprocess.run",
        side_effect=_run_factory(recorded),
    ), patch(
        "atdd.coach.commands.branch.resolve_default_branch",
        return_value="main",
    ), patch(
        "atdd.coach.utils.repo.detect_worktree_layout",
        return_value="worktree-ready",
    ), patch(
        "atdd.coach.commands.initializer.write_workspace",
        return_value=None,
    ):
        mgr = BranchManager(target_dir=tmp_path)
        mgr.branch(issue_number=2)

    fetch_calls = [c for c in recorded if c[:2] == ["git", "fetch"]]
    assert fetch_calls, "No git fetch call recorded"

    targeted = [c for c in fetch_calls if "main" in c]
    assert targeted, (
        f"Expected at least one targeted 'git fetch origin main' call, got fetches: {fetch_calls}"
    )


def test_fetch_precedes_worktree_add(tmp_path):
    """git fetch origin <default_branch> must appear before git worktree add."""
    _make_manifest(tmp_path, issue_number=3, slug="fetch-order")
    recorded: list = []

    with patch(
        "atdd.coach.commands.branch.subprocess.run",
        side_effect=_run_factory(recorded),
    ), patch(
        "atdd.coach.commands.branch.resolve_default_branch",
        return_value="main",
    ), patch(
        "atdd.coach.utils.repo.detect_worktree_layout",
        return_value="worktree-ready",
    ), patch(
        "atdd.coach.commands.initializer.write_workspace",
        return_value=None,
    ):
        mgr = BranchManager(target_dir=tmp_path)
        mgr.branch(issue_number=3)

    fetch_idx = next(
        (i for i, c in enumerate(recorded) if c[:2] == ["git", "fetch"] and "main" in c),
        None,
    )
    wt_idx = next(
        (i for i, c in enumerate(recorded) if c[:3] == ["git", "worktree", "add"]),
        None,
    )
    assert fetch_idx is not None, "No targeted git fetch found"
    assert wt_idx is not None, "No git worktree add found"
    assert fetch_idx < wt_idx, (
        f"git fetch (idx {fetch_idx}) must come before git worktree add (idx {wt_idx})"
    )
