# URN: test:govern-lifecycle:close-substrate-friction-regressions:E030-UNIT-001-all-skip-flags-absent-from-hooks
# Acceptance: acc:govern-lifecycle:E030-UNIT-001-all-skip-flags-absent-from-hooks
# WMBT: wmbt:govern-lifecycle:E030
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-001: All 5 remaining ATDD_SKIP_* flags are absent from every hook template
source file after the 2026-05-26 full-retirement directive.

RED state: All 5 flags are still present in hook source files (retained from E026
audit-logged-bypass phase). Tests fail because retirement has not been applied yet.
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

_RETIRED_FLAGS = [
    "ATDD_SKIP_BARE_CHECK",
    "ATDD_SKIP_VERSION_GATE",
    "ATDD_SKIP_PREPUSH_VALIDATE",
    "ATDD_SKIP_MANIFEST_CHECK",
    "ATDD_SKIP_MASSDELETE",
]


def _hook_text(name: str) -> str:
    p = HOOKS_DIR / name
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def test_atdd_skip_bare_check_absent_from_all_hooks():
    """AC-UNIT-001: ATDD_SKIP_BARE_CHECK must not appear in any hook file."""
    violations = [
        name for name in _HOOK_FILES
        if "ATDD_SKIP_BARE_CHECK" in _hook_text(name)
    ]
    assert not violations, (
        "ATDD_SKIP_BARE_CHECK still present in: " + ", ".join(violations) + "\n"
        "Per 2026-05-26 directive: retire unconditionally. "
        "If core.bare=true blocks a legitimate push, use: atdd emergency --reason '<reason>'"
    )


def test_atdd_skip_version_gate_absent_from_all_hooks():
    """AC-UNIT-001: ATDD_SKIP_VERSION_GATE must not appear in any hook file."""
    violations = [
        name for name in _HOOK_FILES
        if "ATDD_SKIP_VERSION_GATE" in _hook_text(name)
    ]
    assert not violations, (
        "ATDD_SKIP_VERSION_GATE still present in: " + ", ".join(violations) + "\n"
        "Per 2026-05-26 directive: retire unconditionally. "
        "If the version gate blocks legitimately, fix the version check predicate."
    )


def test_atdd_skip_prepush_validate_absent_from_all_hooks():
    """AC-UNIT-001: ATDD_SKIP_PREPUSH_VALIDATE must not appear in any hook file."""
    violations = [
        name for name in _HOOK_FILES
        if "ATDD_SKIP_PREPUSH_VALIDATE" in _hook_text(name)
    ]
    assert not violations, (
        "ATDD_SKIP_PREPUSH_VALIDATE still present in: " + ", ".join(violations) + "\n"
        "Per 2026-05-26 directive: retire unconditionally. "
        "If a stale acceptance blocks the push, fix the stale acceptance."
    )


def test_atdd_skip_manifest_check_absent_from_all_hooks():
    """AC-UNIT-001: ATDD_SKIP_MANIFEST_CHECK must not appear in any hook file."""
    violations = [
        name for name in _HOOK_FILES
        if "ATDD_SKIP_MANIFEST_CHECK" in _hook_text(name)
    ]
    assert not violations, (
        "ATDD_SKIP_MANIFEST_CHECK still present in: " + ", ".join(violations) + "\n"
        "Per 2026-05-26 directive: retire unconditionally. "
        "If the branch is not in manifest, run: atdd issue reconcile"
    )


def test_atdd_skip_massdelete_absent_from_all_hooks():
    """AC-UNIT-001: ATDD_SKIP_MASSDELETE must not appear in any hook file."""
    violations = [
        name for name in _HOOK_FILES
        if "ATDD_SKIP_MASSDELETE" in _hook_text(name)
    ]
    assert not violations, (
        "ATDD_SKIP_MASSDELETE still present in: " + ", ".join(violations) + "\n"
        "Per 2026-05-26 directive: retire unconditionally. "
        "Use commit title prefix (chore(decom):, refactor(remove):) or "
        "[mass-delete-approved] token instead."
    )


def test_no_retired_flag_in_any_hook():
    """AC-UNIT-001: consolidated check — none of the 5 retired flags in any hook."""
    violations = []
    for hook_name in _HOOK_FILES:
        text = _hook_text(hook_name)
        for flag in _RETIRED_FLAGS:
            if flag in text:
                violations.append(f"{hook_name}: {flag}")
    assert not violations, (
        "Bypass flags still present in hook source files (2026-05-26 full retirement):\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\nAll ATDD_SKIP_* flags must be unconditionally removed. "
        "Use: atdd emergency --reason '<reason>' for genuine emergencies."
    )
