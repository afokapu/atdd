# URN: test:govern-lifecycle:agnostic-git-config-bare-guard-via-path-shim:E036-UNIT-003-validate-fails-on-poisoned-baseline
# Acceptance: acc:govern-lifecycle:E036-UNIT-003-validate-fails-on-poisoned-baseline
# WMBT: wmbt:govern-lifecycle:E036
# Phase: RED
# Layer: coach.validator
"""AC-UNIT-003: a coach validator fails on a poisoned core.bare=true baseline.

Run by ``atdd validate`` (coach phase), this validator catches a shared
.git/config that has been poisoned with core.bare=true — regardless of which
agent wrote it — while a worktree-scoped core.bare=false override (effective
false) passes. It complements the agent-agnostic .atdd/bin/git PATH shim (the
prevention layer) as defense-in-depth detection.

  - test_poisoned_baseline_fails_check  — effective core.bare=true → violation
  - test_clean_baseline_passes_check     — effective core.bare=false → clean
  - test_live_repo_baseline_is_not_poisoned — the real CI guard against this repo

RED state: src/atdd/coach/validators/_core_bare_baseline.py does not exist yet.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.coach]

REPO_ROOT = find_repo_root()


def _load_baseline_module():
    try:
        from atdd.coach.validators import _core_bare_baseline
    except ImportError:
        pytest.fail("RED: src/atdd/coach/validators/_core_bare_baseline.py not implemented yet")
    return _core_bare_baseline


def _make_repo(tmp_path: Path, *, core_bare: str) -> Path:
    repo = tmp_path / f"repo_{core_bare}"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "config", "core.bare", core_bare], cwd=str(repo), check=True, capture_output=True)
    return repo


def test_poisoned_baseline_fails_check(tmp_path: Path) -> None:
    mod = _load_baseline_module()
    repo = _make_repo(tmp_path, core_bare="true")
    violations = mod.check_core_bare_not_poisoned(repo)
    assert violations, "poisoned core.bare=true baseline was not flagged"
    assert any("--worktree" in v for v in violations), f"repair pointer missing from violations: {violations!r}"


def test_clean_baseline_passes_check(tmp_path: Path) -> None:
    mod = _load_baseline_module()
    repo = _make_repo(tmp_path, core_bare="false")
    violations = mod.check_core_bare_not_poisoned(repo)
    assert violations == [], f"clean core.bare=false baseline was wrongly flagged: {violations!r}"


def test_live_repo_baseline_is_not_poisoned() -> None:
    """The actual CI guard: this repo's effective core.bare must not be true."""
    mod = _load_baseline_module()
    violations = mod.check_core_bare_not_poisoned(REPO_ROOT)
    assert violations == [], (
        "This repo's shared .git/config is poisoned (core.bare=true). "
        f"Repair: git config --worktree core.bare false. Violations: {violations!r}"
    )
