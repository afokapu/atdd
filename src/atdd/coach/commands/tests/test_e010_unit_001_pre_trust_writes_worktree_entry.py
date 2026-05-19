# URN: test:spawn-agents:worker-launch-prompt-readiness-gate:E010-UNIT-001-pre-trust-writes-worktree-entry
# Acceptance: acc:spawn-agents:E010-UNIT-001-pre-trust-writes-worktree-entry
# WMBT: wmbt:spawn-agents:E010
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E010-UNIT-001 — _pre_trust_worktree writes a projects entry for the
worktree into ~/.claude.json with hasTrustDialogAccepted:true before any
surface is created, so the workspace-trust modal is never shown.

RED: _pre_trust_worktree does not exist in spawn.py yet. The coach currently
has no pre-trust step — fresh worktrees always trigger the workspace-trust
modal, causing the launch prompt to be swallowed (issue #795).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_pre_trust_writes_trust_accepted(tmp_path):
    from atdd.coach.commands.spawn import _pre_trust_worktree

    worktree = tmp_path / "issue-795"
    worktree.mkdir()
    claude_json = tmp_path / ".claude.json"

    _pre_trust_worktree(worktree, claude_json)

    data = json.loads(claude_json.read_text())
    assert data["projects"][str(worktree)]["hasTrustDialogAccepted"] is True


def test_pre_trust_non_destructive_merge(tmp_path):
    """Calling _pre_trust_worktree twice does not lose existing entries."""
    from atdd.coach.commands.spawn import _pre_trust_worktree

    worktree_a = tmp_path / "issue-a"
    worktree_b = tmp_path / "issue-b"
    worktree_a.mkdir()
    worktree_b.mkdir()
    claude_json = tmp_path / ".claude.json"

    # Pre-seed with an existing project entry.
    claude_json.write_text(json.dumps({"projects": {str(worktree_a): {"hasTrustDialogAccepted": True}}}))

    _pre_trust_worktree(worktree_b, claude_json)

    data = json.loads(claude_json.read_text())
    # Both entries survive.
    assert data["projects"][str(worktree_a)]["hasTrustDialogAccepted"] is True
    assert data["projects"][str(worktree_b)]["hasTrustDialogAccepted"] is True


def test_pre_trust_creates_file_if_absent(tmp_path):
    from atdd.coach.commands.spawn import _pre_trust_worktree

    worktree = tmp_path / "fresh-worktree"
    worktree.mkdir()
    claude_json = tmp_path / ".claude.json"
    assert not claude_json.exists()

    _pre_trust_worktree(worktree, claude_json)

    assert claude_json.exists()
    data = json.loads(claude_json.read_text())
    assert str(worktree) in data["projects"]
