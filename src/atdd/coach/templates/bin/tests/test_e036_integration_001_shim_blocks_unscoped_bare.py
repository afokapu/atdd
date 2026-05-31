# URN: test:govern-lifecycle:agnostic-git-config-bare-guard-via-path-shim:E036-INTEGRATION-001-shim-blocks-unscoped-bare
# Acceptance: acc:govern-lifecycle:E036-INTEGRATION-001-shim-blocks-unscoped-bare
# WMBT: wmbt:govern-lifecycle:E036
# Phase: RED
# Layer: backend.integration
"""AC-INTEGRATION-001: `git config core.bare true` through the installed shim
exits 1 and never reaches the real git, with stderr naming the --worktree fix.

RED state: src/atdd/coach/templates/bin/git.shim does not exist yet.
"""
from __future__ import annotations

import pytest

from .conftest import GIT_SHIM_TEMPLATE, REPO_ROOT, run_git_via_shim

pytestmark = [pytest.mark.coach]


def test_shim_blocks_unscoped_bare_and_does_not_forward(git_shim_worktree) -> None:
    assert GIT_SHIM_TEMPLATE.exists(), f"RED: {GIT_SHIM_TEMPLATE.relative_to(REPO_ROOT)} not implemented yet"
    worktree, real_bin, record = git_shim_worktree
    result = run_git_via_shim(worktree, real_bin, ["config", "core.bare", "true"])
    assert result.returncode == 1, f"expected exit 1, got {result.returncode}: {result.stderr}"
    assert "git config --worktree" in result.stderr, f"scoped alternative missing: {result.stderr!r}"
    assert not record.exists(), "real git was invoked despite the shim block — poison write reached the real binary"
