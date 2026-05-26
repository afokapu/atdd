# URN: test:govern-lifecycle:close-substrate-friction-regressions:E026-UNIT-002-retired-flags-absent-from-hook-source
# Acceptance: acc:govern-lifecycle:E026-UNIT-002-retired-flags-absent-from-hook-source
# WMBT: wmbt:govern-lifecycle:E026
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-002: ATDD_SKIP_ALL_GATES, ATDD_SKIP_POSTCOMMIT, and ATDD_SKIP_REGISTRY_CHECK
are absent from all hook source files after retirement.

RED state: All three flags are still present in hook source files. Tests fail
because the retirement has not been applied yet.
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
    "ATDD_SKIP_ALL_GATES",
    "ATDD_SKIP_POSTCOMMIT",
    "ATDD_SKIP_REGISTRY_CHECK",
]


def _hook_text(name: str) -> str:
    p = HOOKS_DIR / name
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def test_atdd_skip_all_gates_absent_from_pre_push():
    """AC-UNIT-002: ATDD_SKIP_ALL_GATES must not appear in pre-push hook."""
    text = _hook_text("pre-push")
    assert "ATDD_SKIP_ALL_GATES" not in text, (
        "pre-push hook still contains ATDD_SKIP_ALL_GATES.\n"
        "Remove the meta-bypass block (lines 10-17 circa v3.82.1). "
        "This flag is retired: individual flags cover all cases."
    )


def test_atdd_skip_postcommit_absent_from_post_commit():
    """AC-UNIT-002: ATDD_SKIP_POSTCOMMIT must not appear in post-commit hook."""
    text = _hook_text("post-commit")
    assert "ATDD_SKIP_POSTCOMMIT" not in text, (
        "post-commit hook still contains ATDD_SKIP_POSTCOMMIT.\n"
        "Remove the env-var check — the hook is advisory (always exits 0); "
        "a bypass of a non-blocking hook is meaningless."
    )


def test_atdd_skip_registry_check_absent_from_pre_push():
    """AC-UNIT-002: ATDD_SKIP_REGISTRY_CHECK must not appear in pre-push hook."""
    text = _hook_text("pre-push")
    assert "ATDD_SKIP_REGISTRY_CHECK" not in text, (
        "pre-push hook still contains ATDD_SKIP_REGISTRY_CHECK.\n"
        "Remove this bypass — E023 auto-heal is live (atdd registry update --yes "
        "runs automatically). The bypass is now redundant."
    )


def test_no_retired_flag_appears_in_any_hook():
    """AC-UNIT-002: none of the 3 retired flags appear in any hook file."""
    violations = []
    for hook_name in _HOOK_FILES:
        text = _hook_text(hook_name)
        for flag in _RETIRED_FLAGS:
            if flag in text:
                violations.append(f"{hook_name}: {flag}")
    assert not violations, (
        "Retired bypass flags still present in hook source files:\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\nRetire these by removing the env-var check blocks."
    )
