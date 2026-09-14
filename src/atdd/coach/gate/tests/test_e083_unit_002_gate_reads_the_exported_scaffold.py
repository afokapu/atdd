# URN: test:govern-lifecycle:enforce-lab-evidence:E083-UNIT-002-gate-reads-the-exported-scaffold
# Acceptance: acc:govern-lifecycle:E083-UNIT-002-gate-reads-the-exported-scaffold
# WMBT: wmbt:govern-lifecycle:E083
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E083-UNIT-002 — the gate READS the generator's scaffold; it does not guess at it.

#1950's lab built the guessing version first: a regex for "placeholder-shaped
prose". It caught `### Setup`, `### Measured result` and `### What it changed about
the plan`, and missed `### Hypothesis` — for no reason but a comma in its prompt.
Three of four, silently, with the check reporting nothing amiss about the fourth.

The fix is not a better regex. It is to stop having two descriptions of the same
strings: the generator writes ``LAB_SCAFFOLD[name]`` and the gate refuses content
that opens with ``LAB_SCAFFOLD[name]``. One source, so a reworded prompt cannot
leave the gate matching a string nobody emits any more.

The last test is the one that would catch a regression to guessing: reword every
prompt, and the gate must follow. A pattern-matching implementation passes the
first two tests here and fails that one.
"""
from __future__ import annotations

import pytest


def _lab_violations():
    try:
        from atdd.coach.gate.lab_evidence_check import lab_violations
    except ImportError:  # pragma: no cover - the RED state
        pytest.fail(
            "atdd.coach.gate.lab_evidence_check.lab_violations not implemented yet — "
            "#1950 GREEN."
        )
    return lab_violations


def _scaffold() -> dict:
    from atdd.planner.commands import author_issue

    scaffold = getattr(author_issue, "LAB_SCAFFOLD", None)
    assert scaffold is not None, (
        "author_issue.LAB_SCAFFOLD not implemented yet — #1950 GREEN"
    )
    return scaffold


def _body_from(scaffold: dict) -> str:
    parts = ["# An issue", "", "## Lab", ""]
    for name in ("Hypothesis", "Setup", "Measured result", "What it changed about the plan"):
        parts += [f"### {name}", "", scaffold[name], ""]
    parts += ["## Phases", ""]
    return "\n".join(parts)


def test_a_freshly_generated_body_reports_all_four_subsections_unfilled():
    """Four of four — the measured failure of the guessing version was three."""
    violations = _lab_violations()(_body_from(_scaffold()))
    assert len(violations) >= 4, (
        f"every scaffold prompt must be recognised as unfilled; got {len(violations)}: "
        f"{violations}"
    )


def test_the_prompt_containing_a_comma_is_recognised():
    """`### Hypothesis` is the one the regex missed. Pinned by name, not by luck."""
    scaffold = _scaffold()
    assert "," in scaffold["Hypothesis"], (
        "this test pins the comma case; if the Hypothesis prompt no longer contains a "
        "comma, choose another prompt whose punctuation defeats naive matching"
    )
    violations = " | ".join(_lab_violations()(_body_from(scaffold)))
    assert "Hypothesis" in violations, (
        "`### Hypothesis` carrying its scaffold prompt must be reported unfilled; "
        "the lab's pattern-matching version missed exactly this one"
    )


def test_rewording_every_prompt_does_not_blind_the_gate():
    """The regression test for a return to guessing.

    Substitute prompts that share no wording with the shipped ones. A gate reading
    ``LAB_SCAFFOLD`` still sees four unfilled subsections; a gate matching patterns
    sees none and waves the issue through.
    """
    reworded = {
        "Hypothesis": "WRITE THE PREMISE HERE, so that it could turn out false",
        "Setup": "WRITE HOW IT WAS CHECKED against the running system",
        "Measured result": "NUMBERS GO HERE",
        "What it changed about the plan": "CONSEQUENCES GO HERE",
    }
    from atdd.planner.commands import author_issue

    original = getattr(author_issue, "LAB_SCAFFOLD", None)
    assert original is not None, "author_issue.LAB_SCAFFOLD not implemented yet — #1950 GREEN"
    author_issue.LAB_SCAFFOLD = reworded
    try:
        violations = _lab_violations()(_body_from(reworded))
    finally:
        author_issue.LAB_SCAFFOLD = original

    assert len(violations) >= 4, (
        f"the gate must follow LAB_SCAFFOLD when it changes; got {len(violations)}: "
        f"{violations}. A gate that only recognises the prompts it was written "
        f"against is the guessing version wearing a constant's name."
    )
