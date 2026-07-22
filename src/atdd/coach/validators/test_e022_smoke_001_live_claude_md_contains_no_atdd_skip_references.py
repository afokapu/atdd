# URN: test:govern-lifecycle:coach-operator-safety-invariants:E064-SMOKE-001-live-claude-md-contains-no-atdd-skip-references
# Acceptance: acc:govern-lifecycle:E068-SMOKE-001-live-claude-md-contains-no-atdd-skip-references
# WMBT: wmbt:govern-lifecycle:E068
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""E022-SMOKE-001 — live CLAUDE.md in the real repo root contains no ATDD_SKIP_* tokens.

SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure.

Confirms that after PR #867 merges, the actual on-disk CLAUDE.md read by every
dispatched worker agent contains zero bypass env-var tokens.  The static UNIT-001
test verifies the committed file; this SMOKE test re-confirms against the live
filesystem post-merge, ensuring no post-merge git hook or tool regenerated the
file with the bad content.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
_BYPASS_PATTERN = re.compile(r"ATDD_SKIP_[A-Z_]+")


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="SMOKE: set ATDD_RUN_SMOKE=1 to run against real infrastructure",
)
def test_live_claude_md_contains_no_atdd_skip_references():
    """E022-SMOKE-001: grep -E ATDD_SKIP_[A-Z_]+ CLAUDE.md returns exit code 1 (no matches)."""
    assert CLAUDE_MD.exists(), f"CLAUDE.md not found at {CLAUDE_MD}"

    # Use subprocess grep to mirror the acceptance criteria exactly
    result = subprocess.run(
        ["grep", "-E", r"ATDD_SKIP_[A-Z_]+", str(CLAUDE_MD)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, (
        f"grep found {len(result.stdout.splitlines())} ATDD_SKIP_* line(s) in CLAUDE.md — "
        "expected exit code 1 (no matches) but got {result.returncode}.\n"
        "Matching lines:\n"
        + result.stdout
        + "\nE022 requires the live CLAUDE.md to have zero bypass tokens post-merge."
    )
    assert result.stdout == "", (
        f"Expected zero output from grep but got:\n{result.stdout}"
    )
