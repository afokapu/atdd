# URN: test:spawn-agents:claude-md-slim-and-debanner:E023-UNIT-001-claude-md-is-at-most-250-lines
# Acceptance: acc:spawn-agents:E023-UNIT-001-claude-md-is-at-most-250-lines
# WMBT: wmbt:spawn-agents:E023
# Phase: RED
# Layer: backend.unit
# Assertion: structural
"""E023-UNIT-001 — CLAUDE.md must be ≤ 250 lines (worker context budget).

Phase RED: fails — CLAUDE.md is 861 lines (pre-#867), well over the 250-line
worker context budget.  High token cost per dispatched agent; low signal-to-noise
ratio because detailed lifecycle scaffolding is inline rather than loadable.

Phase GREEN: E023 slims CLAUDE.md to ≤ 250 lines by moving detailed
implementation notes to conventions files and docs/.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

_LINE_BUDGET = 250


def test_claude_md_is_at_most_250_lines():
    """E023-UNIT-001: wc -l CLAUDE.md reports ≤ 250 lines."""
    assert CLAUDE_MD.exists(), f"CLAUDE.md not found at {CLAUDE_MD}"

    lines = CLAUDE_MD.read_text(encoding="utf-8").splitlines()
    line_count = len(lines)

    assert line_count <= _LINE_BUDGET, (
        f"CLAUDE.md has {line_count} lines — exceeds the {_LINE_BUDGET}-line worker "
        "context budget by {line_count - _LINE_BUDGET} lines.\n"
        "E023 requires CLAUDE.md to be trimmed to ≤ 250 lines.\n"
        "Strategy: move detailed implementation notes (incident narratives, "
        "full lifecycle scaffolding, micro-commit discipline paragraphs) to "
        "conventions files under src/atdd/; keep only the high-signal skeleton "
        "(lifecycle phase names, atdd gate invocation, command pointers)."
    )
