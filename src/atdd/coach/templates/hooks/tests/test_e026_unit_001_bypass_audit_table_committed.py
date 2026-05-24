# URN: test:govern-lifecycle:close-substrate-friction-regressions:E026-UNIT-001-bypass-audit-table-committed
# Acceptance: acc:govern-lifecycle:E026-UNIT-001-bypass-audit-table-committed
# WMBT: wmbt:govern-lifecycle:E026
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-001: docs/bypass-audit.md exists and documents all 7 original bypass
flags with retire/keep decisions.

RED state: docs/bypass-audit.md does not exist yet. Tests fail because the
audit table has not been committed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[6]
AUDIT_TABLE = REPO_ROOT / "docs" / "bypass-audit.md"

_ORIGINAL_FLAGS = [
    "ATDD_SKIP_MANIFEST_CHECK",
    "ATDD_SKIP_VERSION_GATE",
    "ATDD_SKIP_PREPUSH_VALIDATE",
    "ATDD_MAX_UNCOMMITTED",
    "ATDD_SKIP_POSTCOMMIT",
    "ATDD_SKIP_BARE_CHECK",
    "ATDD_SKIP_ALL_GATES",
]

_RETIRED_FLAGS = [
    "ATDD_SKIP_ALL_GATES",
    "ATDD_SKIP_POSTCOMMIT",
    "ATDD_SKIP_REGISTRY_CHECK",
]

_KEPT_FLAGS = [
    "ATDD_SKIP_BARE_CHECK",
    "ATDD_SKIP_MANIFEST_CHECK",
    "ATDD_SKIP_PREPUSH_VALIDATE",
    "ATDD_SKIP_VERSION_GATE",
]


def test_bypass_audit_table_exists():
    """AC-UNIT-001: docs/bypass-audit.md must exist in the repo."""
    assert AUDIT_TABLE.exists(), (
        f"docs/bypass-audit.md not found at {AUDIT_TABLE}.\n"
        "Create the bypass audit table documenting all 7 original flags with retire/keep decisions."
    )


def test_bypass_audit_table_documents_all_original_flags():
    """AC-UNIT-001: each of the 7 original flags appears in the audit table."""
    if not AUDIT_TABLE.exists():
        pytest.skip("audit table not yet created — RED")
    content = AUDIT_TABLE.read_text(encoding="utf-8")
    missing = [f for f in _ORIGINAL_FLAGS if f not in content]
    assert not missing, (
        f"docs/bypass-audit.md is missing entries for: {missing}\n"
        "Every flag from the original 7-flag inventory must have a row."
    )


def test_bypass_audit_table_has_retired_section():
    """AC-UNIT-001: audit table documents the 3 retired flags."""
    if not AUDIT_TABLE.exists():
        pytest.skip("audit table not yet created — RED")
    content = AUDIT_TABLE.read_text(encoding="utf-8")
    missing = [f for f in _RETIRED_FLAGS if f not in content]
    assert not missing, (
        f"docs/bypass-audit.md must document retired flags: {missing}"
    )


def test_bypass_audit_table_has_kept_section():
    """AC-UNIT-001: audit table documents the 4 kept flags."""
    if not AUDIT_TABLE.exists():
        pytest.skip("audit table not yet created — RED")
    content = AUDIT_TABLE.read_text(encoding="utf-8")
    missing = [f for f in _KEPT_FLAGS if f not in content]
    assert not missing, (
        f"docs/bypass-audit.md must document kept flags: {missing}"
    )
