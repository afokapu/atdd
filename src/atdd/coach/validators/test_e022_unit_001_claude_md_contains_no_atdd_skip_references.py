# URN: test:spawn-agents:claude-md-slim-and-debanner:E022-UNIT-001-claude-md-contains-no-atdd-skip-references
# Acceptance: acc:spawn-agents:E022-UNIT-001-claude-md-contains-no-atdd-skip-references
# WMBT: wmbt:spawn-agents:E022
# Phase: RED
# Layer: backend.unit
# Assertion: structural
"""E022-UNIT-001 — CLAUDE.md must contain zero ATDD_SKIP_* env-var references.

Phase RED: fails — CLAUDE.md (861 lines, pre-#867) contains at least one
ATDD_SKIP_* token (e.g. ATDD_SKIP_POSTCOMMIT=1 in the post_commit_hook.overrides
section).  The bypass-discovery vector is present.

Phase GREEN: E022 edits remove every ATDD_SKIP_* token from CLAUDE.md;
this test confirms the literal pattern is absent.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

_BYPASS_PATTERN = re.compile(r"ATDD_SKIP_[A-Z_]+")


def test_claude_md_contains_no_atdd_skip_references():
    """E022-UNIT-001: grep ATDD_SKIP_[A-Z_]+ CLAUDE.md returns 0 lines."""
    assert CLAUDE_MD.exists(), f"CLAUDE.md not found at {CLAUDE_MD}"

    text = CLAUDE_MD.read_text(encoding="utf-8")
    lines = text.splitlines()

    matching = [
        (i + 1, line)
        for i, line in enumerate(lines)
        if _BYPASS_PATTERN.search(line)
    ]

    assert matching == [], (
        f"CLAUDE.md contains {len(matching)} ATDD_SKIP_* reference(s) — "
        "E022 requires zero bypass tokens in the agent context file.\n"
        "Offending lines:\n"
        + "\n".join(f"  L{lineno}: {line.rstrip()}" for lineno, line in matching)
        + "\nFix: strip every ATDD_SKIP_* token and replace with a pointer to "
        "docs/operator-emergency-bypass.md"
    )
