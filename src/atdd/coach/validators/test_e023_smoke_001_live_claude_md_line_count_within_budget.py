# URN: test:govern-lifecycle:coach-operator-safety-invariants:E065-SMOKE-001-live-claude-md-line-count-within-budget
# Acceptance: acc:govern-lifecycle:E065-SMOKE-001-live-claude-md-line-count-within-budget
# WMBT: wmbt:govern-lifecycle:E065
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""E023-SMOKE-001 — live CLAUDE.md in the real repo root is ≤ 250 lines after PR #867 merges.

SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure.

Confirms the deployed CLAUDE.md meets the context-budget constraint on the live
filesystem, ruling out post-merge regeneration or drift that would re-inflate the
line count.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
_LINE_BUDGET = 250


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_live_claude_md_line_count_within_budget():
    """E023-SMOKE-001: wc -l CLAUDE.md reports ≤ 250 on the live filesystem."""
    assert CLAUDE_MD.exists(), f"CLAUDE.md not found at {CLAUDE_MD}"

    # wc -l mirrors the acceptance criteria verbatim
    result = subprocess.run(
        ["wc", "-l", str(CLAUDE_MD)],
        capture_output=True,
        text=True,
        check=True,
    )
    # wc -l output: "  <count> <filename>"
    line_count = int(result.stdout.strip().split()[0])

    assert line_count <= _LINE_BUDGET, (
        f"Live CLAUDE.md has {line_count} lines — exceeds the {_LINE_BUDGET}-line "
        f"worker context budget by {line_count - _LINE_BUDGET} lines.\n"
        "E023 requires the deployed CLAUDE.md to stay within budget post-merge."
    )
