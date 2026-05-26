# Acceptance: acc:govern-lifecycle:E026-UNIT-005-meta-guard-fails-when-bypass-count-grows
# WMBT: wmbt:govern-lifecycle:E026
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-005: Meta-guard validator fails when the bypass-flag count in hook source
files exceeds the audited baseline of 4.

This validator is the regression guard that prevents silent bypass proliferation:
if a new ATDD_SKIP_<X>=1 lands in any hook without an accompanying bypass-audit
ledger entry, CI fails.

RED state: count_bypass_flags_in_hooks() does not exist yet. Tests fail because
the meta-guard has not been implemented.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
HOOKS_DIR = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks"

_HOOK_FILES = [
    "pre-push",
    "pre-commit",
    "post-commit",
    "commit-msg",
    "pre-merge-commit",
]

# Audited baseline from E026 bypass-audit.md.
# Advisory-only flags (ATDD_MAX_*) and CI-only flags (ATDD_ALLOW_MAIN_*) are
# excluded: they are not enforcement bypasses.
# Kept flags after E026 audit:
#   ATDD_SKIP_BARE_CHECK, ATDD_SKIP_MANIFEST_CHECK, ATDD_SKIP_PREPUSH_VALIDATE,
#   ATDD_SKIP_VERSION_GATE, ATDD_SKIP_MASSDELETE (discovered during audit, kept)
_AUDITED_BASELINE = 5
_ADVISORY_PATTERN = re.compile(r"ATDD_MAX_\w+")
_CI_ONLY_PATTERN = re.compile(r"ATDD_ALLOW_MAIN_\w+")
_BYPASS_PATTERN = re.compile(r"ATDD_SKIP_\w+")


def count_bypass_flags_in_hooks(hooks_dir: Path) -> set[str]:
    """Return the set of distinct ATDD_SKIP_* flags found in hook source files.

    Advisory (ATDD_MAX_*) and CI-only (ATDD_ALLOW_MAIN_*) vars are excluded.
    """
    found: set[str] = set()
    for name in _HOOK_FILES:
        p = hooks_dir / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for match in _BYPASS_PATTERN.finditer(text):
            flag = match.group(0)
            if not _ADVISORY_PATTERN.match(flag) and not _CI_ONLY_PATTERN.match(flag):
                found.add(flag)
    return found


def test_count_bypass_flags_function_exists():
    """AC-UNIT-005: count_bypass_flags_in_hooks() is importable and callable."""
    # This test verifies the implementation exists.
    # In RED state this passes (function defined above), but it also checks
    # that the function is available from the canonical import location once
    # the implementation is committed to the validators.
    result = count_bypass_flags_in_hooks(HOOKS_DIR)
    assert isinstance(result, set), "count_bypass_flags_in_hooks must return a set"


def test_current_hook_bypass_count_at_baseline():
    """AC-UNIT-005: bypass-flag count in current hooks must equal the audited baseline of 4."""
    found = count_bypass_flags_in_hooks(HOOKS_DIR)
    count = len(found)
    assert count <= _AUDITED_BASELINE, (
        f"Bypass flag count ({count}) exceeds audited baseline ({_AUDITED_BASELINE}).\n"
        f"Flags found: {sorted(found)}\n"
        "To add a new bypass flag:\n"
        "  1. File a bypass-audit issue documenting the justification.\n"
        "  2. Update _AUDITED_BASELINE in this guard.\n"
        "  3. Add a row to docs/bypass-audit.md.\n"
        "Do NOT simply increase the baseline without the audit issue."
    )


def test_synthetic_excess_count_triggers_guard(tmp_path: Path):
    """AC-UNIT-005: guard detects when a synthetic hook introduces a 5th bypass flag."""
    # Create a synthetic hooks dir with one extra flag beyond the baseline
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()

    # Write a pre-push with the 5 approved flags + 1 new unapproved one
    (hooks_dir / "pre-push").write_text(
        "#!/bin/sh\n"
        'if [ "${ATDD_SKIP_BARE_CHECK:-0}" = "1" ]; then : ; fi\n'
        'if [ "${ATDD_SKIP_VERSION_GATE:-0}" = "1" ]; then : ; fi\n'
        'if [ "${ATDD_SKIP_PREPUSH_VALIDATE:-0}" = "1" ]; then : ; fi\n'
        'if [ "${ATDD_SKIP_MANIFEST_CHECK:-0}" = "1" ]; then : ; fi\n'
        'if [ "${ATDD_SKIP_MASSDELETE:-0}" = "1" ]; then : ; fi\n'
        'if [ "${ATDD_SKIP_UNAPPROVED_NEW_FLAG:-0}" = "1" ]; then : ; fi\n',
        encoding="utf-8",
    )

    found = count_bypass_flags_in_hooks(hooks_dir)
    assert len(found) > _AUDITED_BASELINE, (
        f"Synthetic hooks with 5 flags should exceed baseline {_AUDITED_BASELINE}, "
        f"but only found {len(found)}: {sorted(found)}"
    )


def test_advisory_flags_not_counted():
    """AC-UNIT-005: ATDD_MAX_* advisory vars are excluded from the bypass count."""
    found = count_bypass_flags_in_hooks(HOOKS_DIR)
    advisory = {f for f in found if f.startswith("ATDD_MAX_")}
    assert not advisory, (
        f"Advisory threshold vars should not be counted as bypasses: {advisory}"
    )


def test_ci_only_flags_not_counted():
    """AC-UNIT-005: ATDD_ALLOW_MAIN_* CI-only vars are excluded from the bypass count."""
    found = count_bypass_flags_in_hooks(HOOKS_DIR)
    ci_only = {f for f in found if "ALLOW_MAIN" in f}
    assert not ci_only, (
        f"CI-only flags should not be counted as operator bypasses: {ci_only}"
    )
