# URN: test:govern-lifecycle:close-substrate-friction-regressions:E030-SMOKE-001-grep-returns-zero-matches
# Acceptance: acc:govern-lifecycle:E030-SMOKE-001-grep-returns-zero-matches
# WMBT: wmbt:govern-lifecycle:E030
# Phase: SMOKE
# Layer: backend.integration
"""
AC-SMOKE-001: grep -rE 'ATDD_SKIP_[A-Z_]+' src/atdd/coach/templates/hooks/ returns
zero matches after E030 full retirement.

This is the L001 meta-SMOKE from the 2026-05-26 operator directive: the hooks must
not even mention ATDD_SKIP_* env vars. A zero-match grep is the authoritative proof
of full retirement.

SMOKE state: runs against real hook source files in the repo. Passes only when
all 5 flags have been removed from all hook template files.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

HOOKS_DIR = Path(__file__).resolve().parents[1]

_SKIP_PATTERN = re.compile(r"ATDD_SKIP_[A-Z_]+")

_HOOK_FILES = [
    "pre-push",
    "pre-commit",
    "post-commit",
    "commit-msg",
    "pre-merge-commit",
]


def test_grep_atdd_skip_returns_zero_matches():
    """AC-SMOKE-001: no ATDD_SKIP_* pattern in any hook template file."""
    matches = []
    for name in _HOOK_FILES:
        p = HOOKS_DIR / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for m in _SKIP_PATTERN.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            matches.append(f"{name}:{line_no}: {m.group(0)}")

    assert not matches, (
        "ATDD_SKIP_* patterns still found in hook template files (L001 violated):\n"
        + "\n".join(f"  {m}" for m in matches)
        + "\n\nPer 2026-05-26 directive: hooks must not even mention bypass env vars.\n"
        "Remove all ATDD_SKIP_* references from every hook file."
    )
