# URN: test:drive-state-machine:consolidate-worktree-command:L002-UNIT-004-worktree-remove-refuses-main-checkout
# Acceptance: acc:drive-state-machine:L002-UNIT-004-worktree-remove-refuses-main-checkout
# WMBT: wmbt:drive-state-machine:L002
# Phase: RED
# Harness: unit
# Layer: application
"""L002-UNIT-004 — `atdd worktree remove` refuses to remove the main checkout.

Issue #1347. `remove` must never tear down the primary checkout: asked to remove
the target_dir itself, it returns non-zero with an explicit refusal and never
shells `git worktree remove` against it.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.branch import BranchManager

pytestmark = [pytest.mark.platform]


def test_l002_unit_004_worktree_remove_refuses_main_checkout(tmp_path, monkeypatch, capsys):
    # The main-checkout guard must return BEFORE any git worktree enumeration or
    # removal runs; reaching _list_worktrees means the short-circuit failed.
    def _boom(self):
        raise AssertionError("guard must short-circuit before touching git worktrees")

    monkeypatch.setattr(BranchManager, "_list_worktrees", _boom)

    rc = BranchManager(tmp_path).remove_worktree(str(tmp_path))

    assert rc == 1
    assert "main checkout" in capsys.readouterr().out.lower()
