# URN: test:author-atdd-substrate:author-issue-body:C015-UNIT-001-generator-emits-lab-from-the-exported-scaffold
# Acceptance: acc:author-atdd-substrate:C015-UNIT-001-generator-emits-lab-from-the-exported-scaffold
# WMBT: wmbt:author-atdd-substrate:C015
# Phase: RED
# Layer: application
"""C015-UNIT-001 — the generator emits `## Lab`, seeded from an EXPORTED constant.

WHY A CONSTANT AND NOT PROSE IN THE TEMPLATE STRING. The INIT->PLANNED gate has to
decide whether a subsection is still unfilled, and it can only do that honestly by
comparing against the very strings the generator wrote. #1950's lab tried the other
way first — a regex guessing at "placeholder-shaped prose" — and it caught three of
the four prompts, missing `### Hypothesis` for no reason but a comma in its text.
Reading ``LAB_SCAFFOLD`` catches four of four and cannot rot: change a prompt here
and the gate follows automatically.

DIRECTION OF THE DEPENDENCY. ``LAB_SCAFFOLD`` lives planner-side, beside
``create_issue_body``, and the coach gate reads it. coach -> planner is the
permitted direction (see this module's own header: "the coach E019 gate may
DELEGATE to validate_issue_body; the dependency points coach -> planner, never the
reverse"). Exporting it from the generator is what keeps that arrow pointing the
right way.
"""
from __future__ import annotations

from ._helpers import get_create_issue_body, sample_spec

_SUBSECTIONS = ("Hypothesis", "Setup", "Measured result", "What it changed about the plan")


def _lab_scaffold() -> dict:
    """The exported scaffold mapping, or fail naming the phase that lands it."""
    from atdd.planner.commands import author_issue

    scaffold = getattr(author_issue, "LAB_SCAFFOLD", None)
    assert scaffold is not None, (
        "atdd.planner.commands.author_issue.LAB_SCAFFOLD not implemented yet — "
        "#1950 GREEN. Without it the gate has no source for the scaffold strings "
        "and must guess at them, which the lab measured at 3 of 4."
    )
    return scaffold


def test_lab_scaffold_declares_all_four_subsections():
    scaffold = _lab_scaffold()
    assert set(scaffold) == set(_SUBSECTIONS), (
        f"LAB_SCAFFOLD must declare exactly the four subsections; got {sorted(scaffold)}"
    )
    for name, prompt in scaffold.items():
        assert isinstance(prompt, str) and prompt.strip(), f"{name} has an empty prompt"


def test_the_generator_emits_the_lab_section_with_its_four_subsections():
    body = get_create_issue_body()(sample_spec())
    assert "## Lab" in body, (
        "create_issue_body does not emit `## Lab` — #1950 GREEN. An issue authored "
        "without the scaffold cannot be held to filling it."
    )
    for name in _SUBSECTIONS:
        assert f"### {name}" in body, f"`### {name}` missing from the emitted body"


def test_each_subsection_is_seeded_from_the_constant_not_a_second_copy():
    """One source for the scaffold strings, or the gate and generator can disagree."""
    scaffold = _lab_scaffold()
    body = get_create_issue_body()(sample_spec())
    for name, prompt in scaffold.items():
        heading = f"### {name}"
        start = body.index(heading) + len(heading)
        nxt = body.find("\n### ", start)
        content = (body[start:nxt] if nxt != -1 else body[start:]).strip()
        content = content.split("\n## ")[0].strip()
        assert content.startswith(prompt), (
            f"`{heading}` content must be seeded from LAB_SCAFFOLD[{name!r}];\n"
            f"  expected to start with: {prompt!r}\n"
            f"  got:                    {content[:80]!r}"
        )
