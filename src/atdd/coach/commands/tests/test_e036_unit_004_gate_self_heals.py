# URN: test:govern-lifecycle:agnostic-git-config-bare-guard-via-path-shim:E036-UNIT-004-gate-self-heals-poisoned-worktree
# Acceptance: acc:govern-lifecycle:E036-UNIT-004-gate-self-heals-poisoned-worktree
# WMBT: wmbt:govern-lifecycle:E036
# Phase: RED
# Layer: backend.integration
"""AC-UNIT-004: atdd gate self-heals a poisoned worktree at session bootstrap.

When the effective core.bare is true, ATDDGate scopes core.bare=false back via
`git config --worktree` (enabling extensions.worktreeConfig as needed). The
self-heal is best-effort: it must never raise, even when --worktree is
unsupported or the dir is not a git repo.

  - test_gate_self_heals_poisoned_repo   — effective core.bare goes true → false
  - test_self_heal_never_raises_off_repo  — best-effort no-op on a non-git dir

RED state: ATDDGate has no self_heal_core_bare() method yet.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.gate import ATDDGate

pytestmark = [pytest.mark.coach]


def _effective_core_bare(repo: Path) -> str:
    return subprocess.run(
        ["git", "config", "--get", "core.bare"],
        cwd=str(repo), capture_output=True, text=True,
    ).stdout.strip().lower()


def test_gate_self_heals_poisoned_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "config", "core.bare", "true"], cwd=str(repo), check=True, capture_output=True)
    assert _effective_core_bare(repo) == "true", "precondition: repo should be poisoned"

    gate = ATDDGate(target_dir=repo)
    assert hasattr(gate, "self_heal_core_bare"), "RED: ATDDGate.self_heal_core_bare() not implemented yet"
    gate.self_heal_core_bare()

    assert _effective_core_bare(repo) == "false", "self-heal did not scope core.bare back to false"


def test_self_heal_never_raises_off_repo(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    gate = ATDDGate(target_dir=not_a_repo)
    assert hasattr(gate, "self_heal_core_bare"), "RED: ATDDGate.self_heal_core_bare() not implemented yet"
    # Best-effort: must return without raising even when there is no git repo.
    gate.self_heal_core_bare()
