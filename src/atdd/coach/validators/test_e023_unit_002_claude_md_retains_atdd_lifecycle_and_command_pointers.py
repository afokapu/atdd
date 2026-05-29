# URN: test:spawn-agents:claude-md-slim-and-debanner:E023-UNIT-002-claude-md-retains-atdd-lifecycle-and-command-pointers
# Acceptance: acc:spawn-agents:E023-UNIT-002-claude-md-retains-atdd-lifecycle-and-command-pointers
# WMBT: wmbt:spawn-agents:E023
# Phase: RED
# Layer: backend.unit
# Assertion: structural
"""E023-UNIT-002 — slimmed CLAUDE.md retains the core lifecycle skeleton.

This is a guard/regression test that ensures the E023 trim does NOT remove
the minimal orientation content workers need at session start:
  - All six phase names (INIT, PLANNED, RED, GREEN, SMOKE, REFACTOR)
  - The 'atdd gate' invocation (mandatory bootstrap step)
  - A reference to the conventions directory (src/atdd/)

Phase RED: the content checks currently PASS on the pre-slim 861-line file
(all required strings are present).  This test acts as a regression guard:
if the coder over-trims and removes any required marker during E023, this
test will FAIL — protecting orientation quality while permitting the slim.

Phase GREEN: still passes — the trimmed CLAUDE.md retains these markers.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

_REQUIRED_STRINGS = [
    "INIT",
    "PLANNED",
    "RED",
    "GREEN",
    "SMOKE",
    "REFACTOR",
    "atdd gate",
    "src/atdd",
]


def test_claude_md_retains_atdd_lifecycle_and_command_pointers():
    """E023-UNIT-002: slimmed CLAUDE.md still contains all core orientation markers."""
    assert CLAUDE_MD.exists(), f"CLAUDE.md not found at {CLAUDE_MD}"

    text = CLAUDE_MD.read_text(encoding="utf-8")

    missing = [s for s in _REQUIRED_STRINGS if s not in text]

    assert missing == [], (
        f"CLAUDE.md is missing {len(missing)} required orientation marker(s) after slim:\n"
        + "\n".join(f"  - '{m}'" for m in missing)
        + "\nE023 requires the slimmed file to retain the ATDD lifecycle phase names, "
        "the 'atdd gate' invocation, and a reference to src/atdd/ conventions.\n"
        "Do not remove these markers when trimming the file."
    )
