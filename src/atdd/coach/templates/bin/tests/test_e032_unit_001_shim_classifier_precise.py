# URN: test:govern-lifecycle:gh-issue-create-block-l3:E032-UNIT-001-shim-classifier-precise
# Acceptance: acc:govern-lifecycle:E032-UNIT-001-shim-classifier-precise
# WMBT: wmbt:govern-lifecycle:E032
# Phase: RED
# Layer: backend.unit
"""AC-UNIT-001: the .atdd/bin/gh shim's argv classifier is precise.

Blocks ``gh issue create`` and ``gh issue create --title x`` (exit 1, real gh
never reached) but forwards ``gh issuecreate``, ``gh issue createfoo``, and
``gh issue create_thing`` unchanged to the next gh on PATH.

RED state: src/atdd/coach/templates/bin/gh.shim does not exist yet, so the
fixture's install step fails with an explicit RED message.
"""
from __future__ import annotations

import pytest

from .conftest import REPO_ROOT, SHIM_TEMPLATE, run_gh_via_shim

pytestmark = [pytest.mark.coach]


def _require_shim() -> None:
    assert SHIM_TEMPLATE.exists(), f"RED: {SHIM_TEMPLATE.relative_to(REPO_ROOT)} not implemented yet"


def test_shim_blocks_exact_issue_create(shim_worktree) -> None:
    _require_shim()
    worktree, real_bin, record = shim_worktree
    result = run_gh_via_shim(worktree, real_bin, ["issue", "create"])
    assert result.returncode == 1, f"expected block (exit 1), got {result.returncode}: {result.stderr}"
    assert "atdd issue" in result.stderr, f"alternative missing from stderr: {result.stderr!r}"
    assert not record.exists(), "real gh was invoked for a blocked `gh issue create`"


def test_shim_blocks_issue_create_with_flags(shim_worktree) -> None:
    _require_shim()
    worktree, real_bin, record = shim_worktree
    result = run_gh_via_shim(worktree, real_bin, ["issue", "create", "--title", "x"])
    assert result.returncode == 1
    assert "atdd issue" in result.stderr
    assert not record.exists(), "real gh was invoked for `gh issue create --title x`"


@pytest.mark.parametrize(
    "args",
    [
        ["issuecreate"],            # $1 is 'issuecreate', not 'issue'
        ["issue", "createfoo"],     # $2 is 'createfoo', not 'create'
        ["issue", "create_thing"],  # $2 is 'create_thing', not 'create'
    ],
)
def test_shim_forwards_near_misses(shim_worktree, args) -> None:
    _require_shim()
    worktree, real_bin, record = shim_worktree
    result = run_gh_via_shim(worktree, real_bin, args)
    assert result.returncode == 0, f"near-miss {args} was wrongly blocked: {result.stderr}"
    assert record.exists(), f"near-miss {args} was not forwarded to the real gh"
    logged = record.read_text()
    assert " ".join(args) in logged, f"forwarded argv {args!r} not recorded: {logged!r}"
