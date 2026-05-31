# URN: test:govern-lifecycle:agnostic-git-config-bare-guard-via-path-shim:E036-INTEGRATION-003-shim-resolves-real-git
# Acceptance: acc:govern-lifecycle:E036-INTEGRATION-003-shim-resolves-real-git
# WMBT: wmbt:govern-lifecycle:E036
# Phase: RED
# Layer: backend.integration
"""AC-INTEGRATION-003: the shim execs the NEXT git in PATH, not itself.

Running `git status` twice through the shim must complete within a bounded
timeout and forward to the recording stub exactly twice (no infinite loop /
recursion).

RED state: src/atdd/coach/templates/bin/git.shim does not exist yet.
"""
from __future__ import annotations

import pytest

from .conftest import GIT_SHIM_TEMPLATE, REPO_ROOT, run_git_via_shim

pytestmark = [pytest.mark.coach]


def test_shim_does_not_loop_on_itself(git_shim_worktree) -> None:
    assert GIT_SHIM_TEMPLATE.exists(), f"RED: {GIT_SHIM_TEMPLATE.relative_to(REPO_ROOT)} not implemented yet"
    worktree, real_bin, record = git_shim_worktree

    first = run_git_via_shim(worktree, real_bin, ["status"])
    assert first.returncode == 0, f"first invocation failed/looped: {first.stderr}"

    second = run_git_via_shim(worktree, real_bin, ["status"])
    assert second.returncode == 0, f"second invocation failed/looped: {second.stderr}"

    assert record.exists(), "real git was never reached"
    lines = [ln for ln in record.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2, f"expected 2 forwarded calls, got {len(lines)}: {lines!r}"
