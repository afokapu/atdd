# URN: test:govern-lifecycle:close-substrate-friction-regressions:E030-UNIT-002-bypass-reason-absent-from-hooks
# Acceptance: acc:govern-lifecycle:E030-UNIT-002-bypass-reason-absent-from-hooks
# WMBT: wmbt:govern-lifecycle:E030
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-002: ATDD_BYPASS_REASON and _emit_bypass_audit no longer appear in any hook
source file after the 2026-05-26 full-retirement directive.

E026 introduced ATDD_BYPASS_REASON as a mandatory companion for kept flags, with
_emit_bypass_audit writing to bypass-audit.jsonl. E030 retires all flags, making the
bypass-reason mechanism itself obsolete and potentially confusing (operators might
try to set ATDD_BYPASS_REASON thinking it still does something).

RED state: ATDD_BYPASS_REASON and _emit_bypass_audit are still present in pre-push,
pre-commit, pre-merge-commit, and commit-msg hook source files.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

HOOKS_DIR = Path(__file__).resolve().parents[1]

_HOOK_FILES = [
    "pre-push",
    "pre-commit",
    "post-commit",
    "commit-msg",
    "pre-merge-commit",
]


def _hook_text(name: str) -> str:
    p = HOOKS_DIR / name
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def test_atdd_bypass_reason_absent_from_all_hooks():
    """AC-UNIT-002: ATDD_BYPASS_REASON must not appear in any hook file."""
    violations = [
        name for name in _HOOK_FILES
        if "ATDD_BYPASS_REASON" in _hook_text(name)
    ]
    assert not violations, (
        "ATDD_BYPASS_REASON still referenced in: " + ", ".join(violations) + "\n"
        "E030 retires all ATDD_SKIP_* flags, making ATDD_BYPASS_REASON obsolete. "
        "Remove the _emit_bypass_audit helper and all ATDD_BYPASS_REASON references."
    )


def test_emit_bypass_audit_helper_absent_from_all_hooks():
    """AC-UNIT-002: _emit_bypass_audit helper must not appear in any hook file."""
    violations = [
        name for name in _HOOK_FILES
        if "_emit_bypass_audit" in _hook_text(name)
    ]
    assert not violations, (
        "_emit_bypass_audit still present in: " + ", ".join(violations) + "\n"
        "E030 removes all bypass flags; _emit_bypass_audit has no remaining callers. "
        "Delete the helper function block."
    )
