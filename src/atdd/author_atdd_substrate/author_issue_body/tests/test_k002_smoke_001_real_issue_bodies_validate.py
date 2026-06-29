# URN: test:author-atdd-substrate:author-issue-body:K002-SMOKE-001-real-issue-bodies-validate
# Acceptance: acc:author-atdd-substrate:K002-SMOKE-001-real-issue-bodies-validate
# WMBT: wmbt:author-atdd-substrate:K002
# Phase: SMOKE
# Layer: integration
"""K002-SMOKE-001 — real existing GitHub issue bodies validate (back-compat, live data).

A checked-in fixture captured from a live GitHub issue (#1223, which passes the
legacy E019 gate) must validate against issue.schema.json — proving the schema
accepts today's real compliant bodies, not only newly-authored ones.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.issue_template import check_body_sections, check_placeholders

from ._helpers import get_validate_issue_body

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.smoke
def test_k002_smoke_001_real_issue_bodies_validate():
    validate_issue_body = get_validate_issue_body()

    real_bodies = sorted(_FIXTURES.glob("*.md"))
    assert real_bodies, "no real issue-body fixtures captured"

    for path in real_bodies:
        body = path.read_text(encoding="utf-8")

        # This fixture is a real body that passes the legacy gate today.
        legacy_ok = not check_body_sections(body) and not check_placeholders(body)
        assert legacy_ok, f"{path.name} is not legacy-compliant; recapture it"

        # No compliant body passing legacy E019 is newly rejected by the schema.
        violations = validate_issue_body(body)
        assert violations == [], (
            f"real compliant body {path.name} newly rejected by schema gate: {violations}"
        )
