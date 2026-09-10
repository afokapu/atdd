# URN: test:govern-lifecycle:placeholder-detection-is-line-anchored:E078-SMOKE-001-a-real-transition-is-not-blocked-by-prose
# Acceptance: acc:govern-lifecycle:E078-SMOKE-001-a-real-transition-is-not-blocked-by-prose
# WMBT: wmbt:govern-lifecycle:E078
# Phase: SMOKE
# Layer: integration
"""E078-SMOKE-001 — a real transition is not blocked by prose (#1904).

The UNIT test drives `check_placeholders`. This drives `check_issue_compliance`,
which is what the transition gate actually calls, over a body shaped like a real
issue.

The case is not hypothetical. Issue #1904 — the issue reporting that 'JTBD' reads
as an unfilled 'TBD' — was itself refused at PLANNED by the installed CLI,
because the authoring template quotes the issue TITLE into the Context table and
that title contains the word "TBD". The defect blocked the fix for the defect,
and the transition needed --force.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.issue_template import (
    OPTIONAL_SECTIONS,
    check_issue_compliance,
    load_required_sections,
)

pytestmark = [pytest.mark.coach]


def _body(context: str) -> str:
    sections = [
        s for s in load_required_sections()
        if s not in OPTIONAL_SECTIONS and s.startswith("## ")
    ]
    parts = []
    for s in sections:
        parts.append(s)
        parts.append("real content" if s != "## Context" else context)
    parts += ["### Graph Context", "real", "### Mirror Across Agents", "real"]
    return "\n\n".join(parts) + "\n"


def test_prose_mentioning_a_placeholder_is_compliant() -> None:
    """The #1904 case, verbatim in shape: the title quoted into Context."""
    report = check_issue_compliance(
        1904,
        _body("| check_placeholders substring-matches, so 'JTBD' reads as an "
              "unfilled TBD | the gap exists today |"),
    )
    assert report.placeholder_hits == [], (
        f"the gate refuses a body that only MENTIONS a placeholder: {report.placeholder_hits}"
    )
    assert report.missing_sections == []


def test_a_genuinely_unfilled_section_is_still_refused() -> None:
    report = check_issue_compliance(1, _body("TBD"))
    assert report.placeholder_hits, "the gate no longer refuses a section left as scaffolding"


def test_the_two_verdicts_differ() -> None:
    """The whole point: a mention and an omission must not look the same."""
    mention = check_issue_compliance(1, _body("we will replace the JTBD wording later"))
    omission = check_issue_compliance(2, _body("TBD"))
    assert mention.placeholder_hits != omission.placeholder_hits
