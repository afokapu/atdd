# URN: test:govern-lifecycle:gh-issue-create-block-l3:E032-INTEGRATION-001-shim-blocks-create
# Acceptance: acc:govern-lifecycle:E032-INTEGRATION-001-shim-blocks-create
# WMBT: wmbt:govern-lifecycle:E032
# Phase: RED
# Layer: backend.integration
"""AC-INTEGRATION-001: gh issue create through the installed shim exits 1 and never reaches real gh.

RED state: src/atdd/coach/templates/bin/gh.shim does not exist yet.
"""
from __future__ import annotations

import pytest

from .conftest import REPO_ROOT, SHIM_TEMPLATE, run_gh_via_shim

pytestmark = [pytest.mark.coach]


def test_shim_blocks_create_and_does_not_forward(shim_worktree) -> None:
    assert SHIM_TEMPLATE.exists(), f"RED: {SHIM_TEMPLATE.relative_to(REPO_ROOT)} not implemented yet"
    worktree, real_bin, record = shim_worktree
    result = run_gh_via_shim(worktree, real_bin, ["issue", "create", "--title", "x", "--body", "y"])
    assert result.returncode == 1, f"expected exit 1, got {result.returncode}: {result.stderr}"
    assert "atdd author issue" in result.stderr, f"alternative missing: {result.stderr!r}"
    assert not record.exists(), "real gh was invoked despite the shim block"
