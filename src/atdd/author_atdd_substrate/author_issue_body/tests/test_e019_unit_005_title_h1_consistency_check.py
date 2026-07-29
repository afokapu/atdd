# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:E019-UNIT-005-title-h1-consistency-check
# Acceptance: acc:govern-lifecycle:E019-UNIT-005-title-h1-consistency-check
# WMBT: wmbt:govern-lifecycle:E019
# Phase: RED
# Layer: application
"""E019-UNIT-005 — the stored title and the body H1 are one fact, checked as one.

``data.title`` and the body's H1 are two representations of the same thing. Once
``--revise`` writes both (E019-UNIT-004), nothing yet stops them being pulled
apart again by some other path — so this is the invariant that makes the repair
stick rather than merely happen once.

Three decisions are pinned here because each one is the difference between a
check people keep and a check people disable:

**No H1 is SKIPPED, not failed.** 619 of the 822 work items in the Control Root
store carry no H1 at all (surveyed 2026-07-29, fence-aware). A check that failed
on them would red-light 75% of the corpus on day one and be switched off within
the week. Absent is not disagreeing; a body with no H1 is the body-shape
schema's gap to close, not this check's to punish.

**Fenced code is not prose.** A body quoting ``# comment`` inside a ``` fence
has not declared a title. Reading it as one is how a naive scan produced 105
false accusations against the same corpus that a fence-aware scan puts at 24.

**Both sides are named.** "title mismatch" is an accusation; "stored title says
X, body H1 says Y" is a diagnosis the operator can act on without opening the
store themselves.
"""
from __future__ import annotations

import pytest


def _extract():
    from atdd.planner.commands.author_issue import extract_issue_title

    return extract_issue_title


def _violations():
    from atdd.planner.commands.author_issue import title_violations

    return title_violations


# ---------------------------------------------------------------------------
# extract_issue_title — which line is the title, and which only looks like one
# ---------------------------------------------------------------------------

def test_h1_is_read_from_the_first_top_level_heading():
    body = "# The real title\n\n## Issue Metadata\n\n# A later H1\n"

    assert _extract()(body) == "The real title"


def test_h1_tolerates_leading_blank_lines_and_trailing_space():
    body = "\n\n#   Spaced out title   \n\n## Scope\n"

    assert _extract()(body) == "Spaced out title"


def test_a_body_with_no_h1_yields_none():
    body = "## Issue Metadata\n\n| Field | Value |\n"

    assert _extract()(body) is None, (
        "a body with no H1 has not declared a title; None is the honest answer"
    )


def test_h2_is_not_mistaken_for_an_h1():
    body = "## Not a title\n\n### Nor this\n"

    assert _extract()(body) is None


@pytest.mark.parametrize("fence", ["```", "~~~", "````"])
def test_hash_lines_inside_a_fenced_block_are_not_the_h1(fence):
    """A shell comment quoted in a fence is code, not a declared title."""
    body = (
        "## Scope\n\n"
        f"{fence}bash\n"
        "# atdd author issue --revise 1639 --body-file body.md\n"
        f"{fence}\n\n"
        "# The actual title\n"
    )

    assert _extract()(body) == "The actual title", (
        "the fence must be closed before an H1 is read — otherwise a body that "
        "merely quotes a command is credited with declaring a title"
    )


def test_an_unclosed_fence_swallows_everything_after_it():
    """An unterminated fence means the rest of the document is code."""
    body = "## Scope\n\n```\n# not a title\n"

    assert _extract()(body) is None


def test_a_fence_is_only_closed_by_its_own_marker():
    body = "```\n~~~\n# still inside the backtick fence\n```\n\n# The title\n"

    assert _extract()(body) == "The title"


# ---------------------------------------------------------------------------
# title_violations — the consistency check itself
# ---------------------------------------------------------------------------

def test_agreement_is_silent():
    body = "# Same on both sides\n\n## Scope\n"

    assert _violations()("Same on both sides", body) == []


def test_disagreement_is_reported_naming_both_sides():
    body = "# Decommission all 17 planner legacy convention monoliths\n\n## Scope\n"
    stored = "Decommission planner legacy convention monoliths; atomize component + interface into nodes"

    violations = _violations()(stored, body)

    assert len(violations) == 1, f"expected exactly one violation, got {violations}"
    message = violations[0]
    assert stored in message, "the stored title must be quoted back — this is a diagnosis, not a verdict"
    assert "Decommission all 17 planner legacy convention monoliths" in message, (
        "the body H1 must be quoted back too; naming one side leaves the "
        "operator to go find the other"
    )


def test_a_body_with_no_h1_is_skipped_not_failed():
    """The explicit no-H1 semantics: SKIP.

    619/822 stored work items carry no H1. Failing them would make this check
    the first thing anyone turns off.
    """
    body = "## Issue Metadata\n\n| Field | Value |\n"

    assert _violations()("Any stored title at all", body) == []


def test_a_hash_line_only_inside_a_fence_is_skipped_not_accused():
    body = "## Scope\n\n```sh\n# plan/_trains/0205-renewal-before-deadline.yaml\n```\n"

    assert _violations()("feat(atdd): TRAIN_STEP edges + journey mode in atdd urn viz", body) == [], (
        "the fenced line is not an H1, so there is nothing to disagree with"
    )


def test_an_empty_stored_title_against_a_declared_h1_disagrees():
    """A blank title is not agreement — it is the absence of the fact the H1 states."""
    body = "# A declared title\n\n## Scope\n"

    assert _violations()("", body) != []


def test_surrounding_whitespace_is_not_a_disagreement():
    body = "# A declared title\n\n## Scope\n"

    assert _violations()("  A declared title  ", body) == []
