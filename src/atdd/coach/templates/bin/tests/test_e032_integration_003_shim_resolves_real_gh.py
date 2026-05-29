# URN: test:govern-lifecycle:gh-issue-create-block-l3:E032-INTEGRATION-003-shim-resolves-real-gh
# Acceptance: acc:govern-lifecycle:E032-INTEGRATION-003-shim-resolves-real-gh
# WMBT: wmbt:govern-lifecycle:E032
# Phase: RED
# Layer: backend.integration
"""AC-INTEGRATION-003: the shim execs the NEXT gh in PATH, not itself — no infinite loop.

Running `gh issue list` twice through the shim must complete within a bounded
timeout and forward to the recording stub exactly twice.

RED state: src/atdd/coach/templates/bin/gh.shim does not exist yet.
"""
from __future__ import annotations

import pytest

from .conftest import REPO_ROOT, SHIM_TEMPLATE, run_gh_via_shim

pytestmark = [pytest.mark.coach]


def test_shim_does_not_loop_on_itself(shim_worktree) -> None:
    assert SHIM_TEMPLATE.exists(), f"RED: {SHIM_TEMPLATE.relative_to(REPO_ROOT)} not implemented yet"
    worktree, real_bin, record = shim_worktree

    first = run_gh_via_shim(worktree, real_bin, ["issue", "list"])
    assert first.returncode == 0, f"first invocation failed/looped: {first.stderr}"

    second = run_gh_via_shim(worktree, real_bin, ["issue", "list"])
    assert second.returncode == 0, f"second invocation failed/looped: {second.stderr}"

    # Exactly two forwarded calls — proves each invocation resolved to the real
    # gh once (not the shim recursing into itself).
    assert record.exists(), "real gh was never reached"
    lines = [ln for ln in record.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2, f"expected 2 forwarded calls, got {len(lines)}: {lines!r}"
