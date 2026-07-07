# URN: test:drive-state-machine:consolidate-worktree-command:L002-UNIT-002-branch-alias-warns-and-delegates
# Acceptance: acc:drive-state-machine:L002-UNIT-002-branch-alias-warns-and-delegates
# WMBT: wmbt:drive-state-machine:L002
# Phase: RED
# Harness: unit
# Layer: application
"""L002-UNIT-002 — `atdd branch <N>` still works, warns deprecated, and delegates.

Issue #1347. `atdd branch` is retained as a deprecation alias: it emits a stderr
warning naming `atdd worktree create` and delegates to the same creation path,
so existing muscle-memory and scripts keep working.
"""
from __future__ import annotations

import sys

import pytest

import atdd.cli as cli
from atdd.coach.commands.branch import BranchManager

pytestmark = [pytest.mark.platform]


def test_l002_unit_002_branch_alias_warns_and_delegates(monkeypatch, capsys):
    calls = {}

    def _fake_branch(self, issue_number, prefix=None):
        calls["issue_number"] = issue_number
        return 0

    monkeypatch.setattr(BranchManager, "branch", _fake_branch)
    monkeypatch.setattr(sys, "argv", ["atdd", "branch", "42"])

    rc = cli.main()

    assert rc == 0
    assert calls == {"issue_number": 42}  # delegates to the same creation path
    err = capsys.readouterr().err
    assert "Deprecated" in err and "atdd worktree create" in err
