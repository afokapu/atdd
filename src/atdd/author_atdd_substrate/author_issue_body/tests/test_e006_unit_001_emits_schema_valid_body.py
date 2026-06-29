# URN: test:author-atdd-substrate:author-issue-body:E006-UNIT-001-emits-schema-valid-body
# Acceptance: acc:author-atdd-substrate:E006-UNIT-001-emits-schema-valid-body
# WMBT: wmbt:author-atdd-substrate:E006
# Phase: RED
# Layer: application
"""E006-UNIT-001 — create_issue_body emits a schema-valid issue body.

The generated body validates against issue.schema.json, carries the required
`### Graph Context` and `### Mirror Across Agents` H3 subsections, and contains
none of issue_template.PLACEHOLDER_STRINGS — compliant by construction.
"""
from __future__ import annotations

from atdd.coach.commands.issue_template import PLACEHOLDER_STRINGS

from ._helpers import get_create_issue_body, get_validate_issue_body, sample_spec


def test_e006_unit_001_emits_schema_valid_body():
    create_issue_body = get_create_issue_body()
    validate_issue_body = get_validate_issue_body()

    body = create_issue_body(sample_spec())
    assert isinstance(body, str) and body.strip(), "generator returned an empty body"

    # Validates against issue.schema.json (the schema-driven gate, not strings).
    violations = validate_issue_body(body)
    assert violations == [], f"emitted body is not schema-valid: {violations}"

    # The two H3 subsections #682 lifted from advisory to mandatory.
    assert "### Graph Context" in body
    assert "### Mirror Across Agents" in body

    # Zero placeholder traps.
    leaked = [p for p in PLACEHOLDER_STRINGS if p in body]
    assert leaked == [], f"emitted body still carries placeholders: {leaked}"
