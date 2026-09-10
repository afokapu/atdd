# URN: test:govern-lifecycle:issue-body-contract-has-one-reader:E076-UNIT-001-one-reader-for-the-body-contract
# Acceptance: acc:govern-lifecycle:E076-UNIT-001-one-reader-for-the-body-contract
# WMBT: wmbt:govern-lifecycle:E076
# Phase: GREEN
# Layer: backend.unit
"""E076-UNIT-001 — the issue-body contract has exactly one reader (#1901).

`check_body_sections` existed twice, under the same name, in two modules, both
parsing the same 12-section PARENT-ISSUE-TEMPLATE.md:

    commands.issue_template     filters OPTIONAL_SECTIONS, enforces REQUIRED_SUBSECTIONS
    validators.test_issue_validation   did neither

So `atdd author issue` produced bodies that satisfied the checker it shares code
with and failed a duplicate that had never learned the rule. Measured over 40 open
atdd-issues before the fix: 38 rejected by the validator's copy ALONE, 0 by the
command alone, 0 clean on both. Not one issue in the repository satisfied both
readers. After: 2 rejected, and both are genuinely hand-written outside the flow.

The fix is deletion, not synchronisation. Two implementations of one contract
cannot be held in step by care — these agreed once, and #682 moved one of them.
"""
from __future__ import annotations

import inspect

import pytest

from atdd.coach.commands import issue_template
from atdd.coach.validators import test_issue_validation as validator

pytestmark = [pytest.mark.coach]


def test_the_validator_uses_the_commands_reader_not_a_copy() -> None:
    """Identity, not equality. A re-implementation that agrees today is what
    this repository already had."""
    assert validator.check_body_sections is issue_template.check_body_sections
    assert validator.load_required_sections is issue_template.load_required_sections


def test_the_validator_module_defines_no_second_implementation() -> None:
    source = inspect.getsource(validator)
    for name in ("def check_body_sections", "def load_required_sections"):
        assert name not in source, (
            f"{name} is defined again in the validator module. The contract is "
            "back to two readers, and they will drift again."
        )


def test_an_optional_section_is_not_required() -> None:
    """`## Rule Wiring` is optional per #682. Requiring it rejected every body
    the authoring command emits."""
    body = "\n".join(
        s for s in issue_template.load_required_sections()
        if s not in issue_template.OPTIONAL_SECTIONS
    ) + "\n### Graph Context\n### Mirror Across Agents\n"

    assert validator.check_body_sections(body) == [], (
        "a body carrying every non-optional section is still rejected"
    )


def test_a_genuinely_missing_section_is_still_reported() -> None:
    """The fix must not turn the check off."""
    required = [
        s for s in issue_template.load_required_sections()
        if s not in issue_template.OPTIONAL_SECTIONS
    ]
    body = "\n".join(required[1:]) + "\n### Graph Context\n### Mirror Across Agents\n"
    assert required[0] in validator.check_body_sections(body)


def test_the_mandatory_subsections_are_now_enforced_here_too() -> None:
    """The drift cost coverage as well as correctness: #682 lifted these H3
    sections from advisory to mandatory in the command, and the validator's copy
    never saw the change."""
    body = "\n".join(
        s for s in issue_template.load_required_sections()
        if s not in issue_template.OPTIONAL_SECTIONS
    )
    missing = validator.check_body_sections(body)
    assert "### Graph Context" in missing
    assert "### Mirror Across Agents" in missing


def test_the_authoring_command_emits_a_body_this_validator_accepts() -> None:
    """THE POINT. The two sides of one contract must agree on the authoring
    command's own output — that is what "same contract" means, and it is the
    thing that was false: every body `atdd author issue` produced was rejected."""
    from atdd.planner.commands.author_issue import create_issue_body

    body = create_issue_body({"title": "probe", "slug": "probe"})
    assert validator.check_body_sections(body) == [], (
        "the authoring command emits a body its own repository rejects"
    )


def test_the_two_contract_SOURCES_are_reconciled_only_by_hand() -> None:
    """Recorded, not fixed here (#1901 follow-up).

    The author renders from `issue.schema.json` (13 required sections); the coach
    validates from `PARENT-ISSUE-TEMPLATE.md` (12). The difference is carried in
    two hand-maintained frozensets:

        OPTIONAL_SECTIONS     = template-only  -> '## Rule Wiring'
        REQUIRED_SUBSECTIONS  = schema-only    -> '### Graph Context', '### Mirror Across Agents'

    Those constants ARE the drift, written down. This test fails the day the two
    sources move again without the constants following — which is how #1901
    happened in the first place.
    """
    from atdd.planner.commands.author_issue import required_sections

    schema = set(required_sections())
    template = set(issue_template.load_required_sections())

    assert template - schema == set(issue_template.OPTIONAL_SECTIONS), (
        "sections the template requires and the schema does not are no longer "
        "exactly OPTIONAL_SECTIONS — the hand-maintained reconciliation has "
        f"slipped: {sorted(template - schema)}"
    )
    assert schema - template == set(issue_template.REQUIRED_SUBSECTIONS), (
        "sections the schema requires and the template does not are no longer "
        "exactly REQUIRED_SUBSECTIONS: "
        f"{sorted(schema - template)}"
    )
