# URN: test:drive-state-machine:consolidate-worktree-command:L002-UNIT-001-worktree-create-dispatches-to-creation
# Acceptance: acc:drive-state-machine:L002-UNIT-001-worktree-create-dispatches-to-creation
# WMBT: wmbt:drive-state-machine:L002
# Phase: RED
# Harness: unit
# Layer: application
"""L002-UNIT-001 — `atdd worktree create <N>` dispatches to worktree creation.

Issue #1347. The consolidated `atdd worktree create` verb routes to the same
worktree-creation path as the former `atdd branch` (BranchManager.branch).
"""
from __future__ import annotations

import sys

import pytest

import atdd.cli as cli
from atdd.coach.commands.branch import BranchManager

pytestmark = [pytest.mark.platform]


def test_l002_unit_001_worktree_create_dispatches_to_creation(monkeypatch):
    calls = {}

    def _fake_branch(self, issue_number, prefix=None):
        calls["issue_number"] = issue_number
        calls["prefix"] = prefix
        return 0

    monkeypatch.setattr(BranchManager, "branch", _fake_branch)
    monkeypatch.setattr(sys, "argv", ["atdd", "worktree", "create", "42"])

    rc = cli.main()

    assert rc == 0
    assert calls == {"issue_number": 42, "prefix": None}
