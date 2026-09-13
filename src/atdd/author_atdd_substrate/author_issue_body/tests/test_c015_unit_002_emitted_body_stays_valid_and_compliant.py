# URN: test:author-atdd-substrate:author-issue-body:C015-UNIT-002-emitted-body-stays-valid-and-compliant
# Acceptance: acc:author-atdd-substrate:C015-UNIT-002-emitted-body-stays-valid-and-compliant
# WMBT: wmbt:author-atdd-substrate:C015
# Phase: RED
# Layer: application
"""C015-UNIT-002 — adding the section must regress NOTHING.

THE MEASUREMENT THAT PUT THIS TEST HERE. #1950's first plan made `## Lab` a required
section of ``issue.schema.json``. Measured over all 400 live issue bodies, that took
compliance from **398/400 to 4/400**, and failed the K002 back-compat acceptance by
construction against closed #1223 — an issue the scope explicitly refuses to
retrofit. The schema is the BODY contract, binding on every issue ever written; lab
evidence is an EDGE contract, binding only on issues moving forward. Putting the
second in the first is a category error the numbers price at 394 issues.

So the third assertion here is the important one, and it is a negative: the schema's
``required`` list must be untouched. It is the guard against the plan reverting to
its first, measured-wrong shape.
"""
from __future__ import annotations

from pathlib import Path

from ._helpers import (
    get_create_issue_body,
    get_validate_issue_body,
    legacy_missing_sections,
    legacy_placeholder_hits,
    load_issue_schema,
    sample_spec,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def test_the_emitted_body_is_schema_valid():
    body = get_create_issue_body()(sample_spec())
    assert "## Lab" in body, "generator does not emit `## Lab` yet — #1950 GREEN"
    assert get_validate_issue_body()(body) == []


def test_the_emitted_body_is_template_compliant():
    """Compliant means: no missing section AND no unfilled placeholder hit.

    The scaffold prompts must NOT register as template placeholders. They are the
    lab gate's business, on the INIT->PLANNED edge — not the body gate's.
    """
    body = get_create_issue_body()(sample_spec())
    assert "## Lab" in body, "generator does not emit `## Lab` yet — #1950 GREEN"
    assert legacy_missing_sections(body) == []
    assert legacy_placeholder_hits(body) == []


def test_the_schema_required_list_is_untouched():
    """The negative assertion: `## Lab` must NOT become a required section."""
    required = load_issue_schema().get("required", [])
    lab_entries = [h for h in required if "Lab" in h or h in {
        "### Hypothesis", "### Setup", "### Measured result",
        "### What it changed about the plan",
    }]
    assert lab_entries == [], (
        f"issue.schema.json must not require the Lab sections {lab_entries} — "
        f"measured, that takes body compliance from 398/400 to 4/400 and fails K002 "
        f"by construction. The obligation belongs on the INIT->PLANNED edge."
    )


def test_the_real_body_fixtures_still_validate():
    """K002's back-compat guarantee, restated here so this change owns it too."""
    validate = get_validate_issue_body()
    fixtures = sorted(_FIXTURES.glob("*.md"))
    assert fixtures, "no real issue-body fixtures captured"
    for path in fixtures:
        body = path.read_text(encoding="utf-8")
        assert validate(body) == [], (
            f"real compliant body {path.name} newly rejected after adding `## Lab`"
        )
