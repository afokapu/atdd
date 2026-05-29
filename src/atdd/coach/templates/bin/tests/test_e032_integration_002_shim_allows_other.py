# URN: test:govern-lifecycle:gh-issue-create-block-l3:E032-INTEGRATION-002-shim-allows-other
# Acceptance: acc:govern-lifecycle:E032-INTEGRATION-002-shim-allows-other
# WMBT: wmbt:govern-lifecycle:E032
# Phase: RED
# Layer: backend.integration
"""AC-INTEGRATION-002: read-path gh subcommands pass through the shim unchanged.

`gh issue view 668`, `gh issue list`, and `gh issue comment 668 -b x` each exit 0
and reach the next gh on PATH with their argv intact.

RED state: src/atdd/coach/templates/bin/gh.shim does not exist yet.
"""
from __future__ import annotations

import pytest

from .conftest import REPO_ROOT, SHIM_TEMPLATE, run_gh_via_shim

pytestmark = [pytest.mark.coach]


@pytest.mark.parametrize(
    "args",
    [
        ["issue", "view", "668"],
        ["issue", "list"],
        ["issue", "comment", "668", "-b", "x"],
    ],
)
def test_shim_forwards_read_path(shim_worktree, args) -> None:
    assert SHIM_TEMPLATE.exists(), f"RED: {SHIM_TEMPLATE.relative_to(REPO_ROOT)} not implemented yet"
    worktree, real_bin, record = shim_worktree
    result = run_gh_via_shim(worktree, real_bin, args)
    assert result.returncode == 0, f"{args} wrongly blocked: {result.stderr}"
    assert record.exists(), f"{args} not forwarded to real gh"
    assert " ".join(args) in record.read_text(), f"forwarded argv {args!r} not recorded"
