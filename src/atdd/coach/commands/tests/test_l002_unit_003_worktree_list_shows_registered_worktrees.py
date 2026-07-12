# URN: test:drive-state-machine:consolidate-worktree-command:L002-UNIT-003-worktree-list-shows-registered-worktrees
# Acceptance: acc:drive-state-machine:L002-UNIT-003-worktree-list-shows-registered-worktrees
# WMBT: wmbt:drive-state-machine:L002
# Phase: RED
# Harness: unit
# Layer: application
"""L002-UNIT-003 — `atdd worktree list` enumerates registered worktrees + branches.

Issue #1347. The new `list` verb prints every registered git worktree with its
path and branch (and, when resolvable, the bound work item).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.branch import BranchManager

pytestmark = [pytest.mark.platform]


def test_l002_unit_003_worktree_list_shows_registered_worktrees(tmp_path, monkeypatch, capsys):
    entries = [
        (tmp_path / "main", "main"),
        (tmp_path / "refactor-do-a-thing", "refactor/do-a-thing"),
    ]
    monkeypatch.setattr(BranchManager, "_list_worktrees", lambda self: entries)

    rc = BranchManager(tmp_path / "main").list_worktrees()

    assert rc == 0
    out = capsys.readouterr().out
    assert "main" in out
    assert "refactor/do-a-thing" in out
    assert str(tmp_path / "refactor-do-a-thing") in out
