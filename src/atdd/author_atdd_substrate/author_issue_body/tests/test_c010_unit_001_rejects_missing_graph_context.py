# URN: test:author-atdd-substrate:author-issue-body:C010-UNIT-001-rejects-missing-graph-context
# Acceptance: acc:author-atdd-substrate:C010-UNIT-001-rejects-missing-graph-context
# WMBT: wmbt:author-atdd-substrate:C010
# Phase: RED
# Layer: application
"""C010-UNIT-001 — the schema-driven validator rejects a missing required section.

A body with `### Graph Context` removed must be rejected by validate_issue_body,
and the failure must name the missing section sourced from issue.schema.json —
not a hard-coded REQUIRED_SUBSECTIONS list.
"""
from __future__ import annotations

from ._helpers import get_validate_issue_body, legacy_compliant_body


def test_c010_unit_001_rejects_missing_graph_context():
    validate_issue_body = get_validate_issue_body()

    compliant = legacy_compliant_body()
    assert "### Graph Context" in compliant
    # Tamper: strip the required Graph Context subsection heading.
    tampered = compliant.replace("### Graph Context", "### Removed Heading")

    violations = validate_issue_body(tampered)

    assert violations, "validator accepted a body missing `### Graph Context`"
    assert any("Graph Context" in v for v in violations), (
        f"failure does not name the missing section: {violations}"
    )
