# URN: test:govern-lifecycle:coach-operator-safety-invariants:E064-UNIT-002-claude-md-references-operator-emergency-bypass-doc
# Acceptance: acc:govern-lifecycle:E064-UNIT-002-claude-md-references-operator-emergency-bypass-doc
# WMBT: wmbt:govern-lifecycle:E064
# Phase: RED
# Layer: backend.unit
# Assertion: structural
"""E022-UNIT-002 — CLAUDE.md must reference docs/operator-emergency-bypass.md.

Phase RED: fails — CLAUDE.md (pre-#867) does not contain the string
'docs/operator-emergency-bypass.md'; there is no pointer directing workers
to the operator-only emergency override documentation.

Phase GREEN: E022 adds a single pointer line in CLAUDE.md such that
agents reading the file are directed to the operator-only doc rather than
finding inline bypass env-var references.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

_REQUIRED_REFERENCE = "docs/operator-emergency-bypass.md"


def test_claude_md_references_operator_emergency_bypass_doc():
    """E022-UNIT-002: CLAUDE.md contains at least one reference to docs/operator-emergency-bypass.md."""
    assert CLAUDE_MD.exists(), f"CLAUDE.md not found at {CLAUDE_MD}"

    text = CLAUDE_MD.read_text(encoding="utf-8")

    assert _REQUIRED_REFERENCE in text, (
        f"CLAUDE.md does not reference '{_REQUIRED_REFERENCE}'.\n"
        "E022 requires CLAUDE.md to direct agents to the operator-only doc "
        "instead of advertising inline bypass tokens.\n"
        f"Fix: add a line referencing '{_REQUIRED_REFERENCE}' in the "
        "post_commit_hook.overrides or emergency section of CLAUDE.md."
    )
