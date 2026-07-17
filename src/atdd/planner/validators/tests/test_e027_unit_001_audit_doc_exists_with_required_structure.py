# URN: test:govern-lifecycle:smoke-false-green-prevention:E027-UNIT-001-audit-doc-exists-with-required-structure
# Acceptance: acc:govern-lifecycle:E027-UNIT-001-audit-doc-exists-with-required-structure
# WMBT: wmbt:govern-lifecycle:E027
# Phase: RED
# Layer: unit
# Assertion: structural
"""
RED: docs/smoke-audit.md must exist, contain a classification table with the
required columns and the four lived-incident acceptance rows, and include a
histogram section.  Currently fails because the file has not been created yet.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.planner, pytest.mark.platform]

_REQUIRED_COLUMNS = [
    "acceptance-URN",
    "entry-point-coverage",
    "assertion-target",
    "handoff-coverage",
    "incident-cross-ref",
]
_REQUIRED_ROWS = [
    "acc:observe-and-correct:E003-SMOKE-001",
    "acc:observe-and-correct:E003-SMOKE-002",
    "acc:observe-and-correct:E004-SMOKE-001",
]


def test_audit_doc_exists():
    """docs/smoke-audit.md must exist at repo root."""
    audit_path = find_repo_root() / "docs" / "smoke-audit.md"
    assert audit_path.exists(), (
        f"docs/smoke-audit.md not found at {audit_path}. "
        "Create it with the required classification table (E027 GREEN phase)."
    )


def test_audit_doc_has_required_columns():
    """docs/smoke-audit.md must contain each required column header."""
    audit_path = find_repo_root() / "docs" / "smoke-audit.md"
    if not audit_path.exists():
        pytest.skip("docs/smoke-audit.md not yet created — see test_audit_doc_exists")
    content = audit_path.read_text()
    for col in _REQUIRED_COLUMNS:
        assert col in content, (
            f"docs/smoke-audit.md missing required column '{col}'. "
            "Add a Markdown table with columns: acceptance-URN, entry-point-coverage, "
            "assertion-target, handoff-coverage, incident-cross-ref."
        )


def test_audit_doc_has_lived_incident_rows():
    """docs/smoke-audit.md must have rows for the four lived-incident acceptances."""
    audit_path = find_repo_root() / "docs" / "smoke-audit.md"
    if not audit_path.exists():
        pytest.skip("docs/smoke-audit.md not yet created — see test_audit_doc_exists")
    content = audit_path.read_text()
    for row_urn in _REQUIRED_ROWS:
        assert row_urn in content, (
            f"docs/smoke-audit.md missing row for '{row_urn}'. "
            "Add a row for each of the four lived-incident acceptances."
        )


def test_audit_doc_has_histogram_section():
    """docs/smoke-audit.md must have a histogram section grouping rows by structural cause."""
    audit_path = find_repo_root() / "docs" / "smoke-audit.md"
    if not audit_path.exists():
        pytest.skip("docs/smoke-audit.md not yet created — see test_audit_doc_exists")
    content = audit_path.read_text().lower()
    has_histogram = "histogram" in content or ("cause" in content and "count" in content)
    assert has_histogram, (
        "docs/smoke-audit.md must include a histogram section grouping rows by structural-bypass cause "
        "(entry-point-coverage / synthetic-fixture / producer-only / handoff-gap)."
    )
