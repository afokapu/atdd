# URN: test:govern-documentation-obligation:check-declaration-integrity:D001-UNIT-001-red-impact-none-without-reason
# Acceptance: acc:govern-documentation-obligation:D001-UNIT-001-red-impact-none-without-reason
# WMBT: wmbt:govern-documentation-obligation:D001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""D001-UNIT-001 — a structurally incomplete declaration is refused, not discharged.

The declaration has exactly two total forms: `impact: change` carrying artifacts, and
`impact: none` carrying a reason. Anything else is malformed. The distinction matters
because a malformed declaration is not an absent obligation — it is an obligation
whose author did not finish stating it, and reading the second as the first is how a
change ships with no record of what it documented.

`impact: none` with an empty reason is the case this file pins. Core enforces that a
reason is PRESENT; core does not judge whether the reason is any good, and neither
does the installed capability.

This check is also the gate on delegation. `atdd.extension.planner.docs` answers an
absent declaration `COULD_NOT_CHECK`, which BLOCKS (atdd-extensions#73), and no stored
work item carries a declaration yet — so delegating before this check has run would
refuse every COMPLETE in the repository. Integrity first is a safety property, not
sequencing taste.

Format-agnostic by construction: declared paths are opaque strings. This check reads no
file content and interprets no path segment, which is what lets core hold the
obligation without holding any documentation policy.

RED state: `atdd.coach.documentation` declares no `check_declaration_integrity`.
"""
from __future__ import annotations


def test_impact_none_without_a_reason_is_incomplete() -> None:
    from atdd.coach.documentation import check_declaration_integrity

    result = check_declaration_integrity(
        declaration={"impact": "none", "reason": ""},
        change_set=[],
    )

    assert result.complete is False, "an unreasoned `impact: none` is not a finished declaration"
    assert any("reason" in f.lower() for f in result.findings), (
        "the check must name what is missing, not merely refuse"
    )


def test_an_incomplete_declaration_produces_no_verdict_of_discharged() -> None:
    from atdd.coach.documentation import check_declaration_integrity

    result = check_declaration_integrity(
        declaration={"impact": "none", "reason": ""},
        change_set=[],
    )

    assert result.discharged is False, (
        "an incomplete declaration must never read as a discharged obligation"
    )


def test_impact_change_with_no_artifacts_is_incomplete() -> None:
    """The other half of the same rule: the two forms are total, so both are checked."""
    from atdd.coach.documentation import check_declaration_integrity

    result = check_declaration_integrity(declaration={"impact": "change", "artifacts": []}, change_set=[])

    assert result.complete is False
    assert result.discharged is False


def test_a_well_formed_impact_none_is_complete() -> None:
    """No over-correction: a positive declaration with a reason is finished and permits."""
    from atdd.coach.documentation import check_declaration_integrity

    result = check_declaration_integrity(
        declaration={"impact": "none", "reason": "implements an already-documented architecture"},
        change_set=[],
    )

    assert result.complete is True
    assert result.discharged is True
