# URN: test:govern-documentation-obligation:delegate-content-judgement:C001-UNIT-001-red-could-not-check-blocks
# Acceptance: acc:govern-documentation-obligation:C001-UNIT-001-red-could-not-check-blocks
# WMBT: wmbt:govern-documentation-obligation:C001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C001-UNIT-001 — an installed capability that could not observe must BLOCK.

The obligation seam has two ways of not-passing and they mean different things. A
capability that ran to completion and found nothing wrong is a pass. A capability
that ran to completion and *could not answer* — its toolchain absent, the tree
unreadable, a render it cannot attribute — has established nothing. Collapsing the
second into the first is the defect this repository has merged in at least three
places already: #1745 (a lookup failure reported as a pass), #1774 ("no mirror
found" read as "nothing to lose"), #1716 (checks that pass when they cannot
observe).

So `COULD_NOT_CHECK` blocks, exactly as `FAIL` blocks, and its reason reaches the
report as data rather than collapsing into an empty clean result.

The four literals are core's, not the extension's. `atdd.extension.planner.docs`
carries a note at the head of its `verdict.py` requiring it to DELEGATE to a core
vocabulary module rather than keep its own copies — "the wire values must be these
four literals either way; that is the part the two units agree on and the part a
drift would break." This module is the side of that agreement core owns.

RED state: `atdd.coach.documentation` declares no `judge_documentation` and no
verdict vocabulary, so both imports below fail.
"""
from __future__ import annotations

import pytest


def _capability_returning(verdict: str, *, reason: str):
    """A stand-in for an installed capability. Not a mock library double: it is a
    real object satisfying the seam's shape, because the seam is a protocol and the
    thing under test is core's reading of the answer, not the extension's work."""

    class _Capability:
        def check(self, declaration, change_set, repo_root):
            from atdd.coach.documentation import DocumentationCheck, Finding

            return DocumentationCheck(
                verdict=verdict,
                findings=[Finding(rule_id="planner.docs.capability", where="<declaration>", message=reason)],
                checked=[],
            )

    return _Capability()


def test_could_not_check_blocks_the_transition() -> None:
    from atdd.coach.documentation import judge_documentation, verdict

    reason = "asciidoctor is not installed, so reference integrity was not established"
    outcome = judge_documentation(
        declaration={"impact": "change", "artifacts": [{"action": "create", "path": "docs/x.adoc"}]},
        change_set=["docs/x.adoc"],
        repo_root=".",
        capability=_capability_returning(verdict.COULD_NOT_CHECK, reason=reason),
    )

    assert outcome.verdict == verdict.COULD_NOT_CHECK
    assert verdict.blocks(outcome.verdict) is True, "an unobserved obligation must not permit"


def test_the_could_not_check_reason_reaches_the_report() -> None:
    from atdd.coach.documentation import judge_documentation, verdict

    reason = "the documentation tree could not be read"
    outcome = judge_documentation(
        declaration={"impact": "change", "artifacts": [{"action": "create", "path": "docs/x.adoc"}]},
        change_set=["docs/x.adoc"],
        repo_root=".",
        capability=_capability_returning(verdict.COULD_NOT_CHECK, reason=reason),
    )

    assert any(reason in f.message for f in outcome.findings), (
        "the reason must reach the report as data; an empty clean result is the failure mode"
    )


def test_could_not_check_is_not_spelled_like_not_applicable() -> None:
    """The distinction is the whole point, so the vocabulary must keep them apart."""
    from atdd.coach.documentation import verdict

    assert verdict.COULD_NOT_CHECK != verdict.NOT_APPLICABLE
    assert verdict.blocks(verdict.COULD_NOT_CHECK) is True
    assert verdict.blocks(verdict.NOT_APPLICABLE) is False
