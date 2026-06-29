# URN: test:author-atdd-substrate:author-issue-body:K002-UNIT-001-existing-bodies-validate
# Acceptance: acc:author-atdd-substrate:K002-UNIT-001-existing-bodies-validate
# WMBT: wmbt:author-atdd-substrate:K002
# Phase: RED
# Layer: application
"""K002-UNIT-001 — existing compliant bodies validate against the schema (back-compat).

A sample of bodies that pass today's E019 string-grep gate must also validate
against issue.schema.json — the schema-driven gate yields the same accept verdict
as the legacy gate, so the cutover regresses no compliant issue.
"""
from __future__ import annotations

from pathlib import Path

from atdd.coach.commands.issue_template import check_body_sections, check_placeholders

from ._helpers import get_validate_issue_body, legacy_compliant_body

_FIXTURES = Path(__file__).parent / "fixtures"


def _sample_bodies() -> list[str]:
    bodies = [legacy_compliant_body()]
    bodies += [p.read_text(encoding="utf-8") for p in sorted(_FIXTURES.glob("*.md"))]
    return bodies


def test_k002_unit_001_existing_bodies_validate():
    validate_issue_body = get_validate_issue_body()

    for body in _sample_bodies():
        # Precondition: each sample is compliant under TODAY's legacy E019 gate.
        legacy_ok = not check_body_sections(body) and not check_placeholders(body)
        assert legacy_ok, "fixture is not legacy-compliant; not a valid back-compat sample"

        # Back-compat guarantee: the schema gate accepts it too (same verdict).
        violations = validate_issue_body(body)
        assert violations == [], (
            f"legacy-compliant body newly rejected by schema gate: {violations}"
        )
