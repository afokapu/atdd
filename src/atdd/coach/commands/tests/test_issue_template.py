"""
Unit tests for template compliance helpers.

SPEC-COACH-ORCH-0010: structured section-by-section feedback.
SPEC-COACH-ORCH-0011: PLANNED+ gate on compliance.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.commands.issue_template import (
    ComplianceReport,
    check_body_sections,
    check_issue_compliance,
    check_placeholders,
    load_required_sections,
)
from atdd.coach.commands.issue_lifecycle import IssueLifecycle

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# load_required_sections — parses the real template
# ---------------------------------------------------------------------------


def test_load_required_sections_returns_all_h2_headings():
    sections = load_required_sections()
    # PARENT-ISSUE-TEMPLATE.md has 11 H2 sections (E010).
    assert len(sections) == 11
    assert "## Issue Metadata" in sections
    assert "## Scope" in sections
    assert "## Release Gate" in sections
    assert "## Notes" in sections
    # Order is preserved.
    assert sections[0] == "## Issue Metadata"


# ---------------------------------------------------------------------------
# check_body_sections
# ---------------------------------------------------------------------------


def test_check_body_sections_flags_missing():
    body = "## Issue Metadata\n\n(content)\n## Scope\n\n(content)\n"
    missing = check_body_sections(body)
    assert "## Issue Metadata" not in missing
    assert "## Scope" not in missing
    assert "## Notes" in missing


def test_check_body_sections_empty_when_all_present():
    required = load_required_sections()
    body = "\n\n".join(f"{s}\n\n(real content, no placeholders)" for s in required)
    assert check_body_sections(body, required=required) == []


# ---------------------------------------------------------------------------
# check_placeholders
# ---------------------------------------------------------------------------


def test_check_placeholders_detects_scope_placeholder():
    body = (
        "## Scope\n\n### In Scope\n\n- (define specific deliverables)\n"
        "## Notes\n\nreal notes here\n"
    )
    hits = check_placeholders(body)
    sections = {h[0] for h in hits}
    assert "## Scope" in sections
    assert any("define specific deliverables" in p for _, p in hits)


def test_check_placeholders_ignores_preamble():
    body = "(define specific deliverables)\n\n## Scope\n\nreal content\n"
    hits = check_placeholders(body)
    assert hits == []


def test_check_placeholders_flags_tbd_literal():
    body = "## Issue Metadata\n\n| Feature | TBD |\n"
    hits = check_placeholders(body)
    assert any(p == "TBD" for _, p in hits)


def test_check_placeholders_none_on_clean_body():
    required = load_required_sections()
    body = "\n\n".join(f"{s}\n\nfully populated content here\n" for s in required)
    assert check_placeholders(body) == []


# ---------------------------------------------------------------------------
# check_issue_compliance
# ---------------------------------------------------------------------------


def test_report_compliant_is_true_when_clean():
    required = load_required_sections()
    body = "\n\n".join(f"{s}\n\nreal content\n" for s in required)
    report = check_issue_compliance(issue_number=1, body=body)
    assert report.compliant
    assert "compliant" in report.format()


def test_report_non_compliant_lists_missing():
    report = check_issue_compliance(issue_number=42, body="## Issue Metadata\n")
    assert not report.compliant
    output = report.format()
    assert "#42" in output
    assert "Missing sections" in output
    assert "## Notes" in output


# ---------------------------------------------------------------------------
# IssueLifecycle.check + compliance gate
# ---------------------------------------------------------------------------


def _clean_body() -> str:
    return "\n\n".join(f"{s}\n\nreal content\n" for s in load_required_sections())


def _dirty_body() -> str:
    return "## Issue Metadata\n\n(partial)\n"


def test_lifecycle_check_returns_zero_on_compliant(capsys):
    lifecycle = IssueLifecycle()
    with patch.object(lifecycle, "_fetch_issue", return_value={"body": _clean_body()}):
        rc = lifecycle.check(1)
    assert rc == 0
    assert "compliant" in capsys.readouterr().out


def test_lifecycle_check_returns_one_on_non_compliant(capsys):
    lifecycle = IssueLifecycle()
    with patch.object(lifecycle, "_fetch_issue", return_value={"body": _dirty_body()}):
        rc = lifecycle.check(1)
    assert rc == 1
    out = capsys.readouterr().out
    assert "non-compliant" in out
    assert "Missing sections" in out


def test_compliance_gate_blocks_planned_transition(capsys):
    lifecycle = IssueLifecycle()
    with patch.object(lifecycle, "_fetch_issue", return_value={"body": _dirty_body()}):
        rc = lifecycle._compliance_gate(1, "PLANNED")
    assert rc == 1
    assert "blocked" in capsys.readouterr().out


def test_compliance_gate_skips_init_transition():
    lifecycle = IssueLifecycle()
    # INIT is not in _COMPLIANCE_REQUIRED_STATUSES — gate should noop.
    rc = lifecycle._compliance_gate(1, "INIT")
    assert rc == 0


def test_compliance_gate_passes_on_clean_body():
    lifecycle = IssueLifecycle()
    with patch.object(lifecycle, "_fetch_issue", return_value={"body": _clean_body()}):
        rc = lifecycle._compliance_gate(1, "RED")
    assert rc == 0
