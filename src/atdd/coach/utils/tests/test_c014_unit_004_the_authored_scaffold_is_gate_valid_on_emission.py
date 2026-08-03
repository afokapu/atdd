# URN: test:author-atdd-substrate:author-issue-body:C014-UNIT-004-the-authored-scaffold-is-gate-valid-on-emission
# Acceptance: acc:author-atdd-substrate:C014-UNIT-004-the-authored-scaffold-is-gate-valid-on-emission
# WMBT: wmbt:author-atdd-substrate:C014
# Phase: RED
# Layer: application
"""C014-UNIT-004 — the authored scaffold does not fail the gate it is destined for.

``atdd author issue`` emitted::

    ### Created

    - The artifact this issue lands.

    ### Modified

    - None so far.

which parses as THREE artifact claims and fails verification, because none of
them is a path any revision can contain. So the toolkit shipped a body that was
schema-valid and gate-invalid at the same time, and the cheapest way for a
worker to satisfy the gate was to DELETE the section — pointing the incentive
away from the record the gate exists to produce.

The repair is an explicitly empty declaration: it parses as zero claims, which
is valid at INIT and a completeness violation at COMPLETE. Honest either way,
and never a false claim.
"""
from __future__ import annotations


def _always_resolves(kind: str, path: str) -> bool:
    """Git agrees with every real path, so only the scaffold's shape is under test."""
    return True


def _sample_spec() -> dict:
    """A minimal valid issue spec — only the title is really needed."""
    return {
        "title": "Sample schema-driven issue",
        "status": "INIT",
        "type": "implementation",
        "branch": "feat/sample-schema-issue",
    }


def _scaffold_body() -> str:
    from atdd.planner.commands.author_issue import create_issue_body

    return create_issue_body(_sample_spec())


def _scaffold_artifacts() -> dict:
    from atdd.coach.commands.issue import IssueManager

    return IssueManager._parse_artifacts(_scaffold_body())


def test_c014_unit_004_the_scaffold_declares_no_false_claims():
    """The emitted bullets parse to zero claims, not to three unresolvable ones."""
    assert _scaffold_artifacts() == {"created": [], "modified": [], "deleted": []}


def _scaffold_section() -> str:
    import re

    section = re.search(r"## Artifacts\s*\n(.*?)(?=\n## |\Z)", _scaffold_body(), re.DOTALL)
    assert section, "the generated body carries no ## Artifacts section"
    return section.group(1)


def test_c014_unit_004_no_scaffold_bullet_is_prose():
    """Every bullet the scaffold emits is a path — and it emits none, by design.

    A bullet is read as a claim about a file, so the empty form cannot be one.
    Whatever bullets DO appear must satisfy the schema's own path definition.
    """
    from atdd.planner.commands.author_issue import is_repo_relative_path

    bullets = [
        line.strip()[2:].strip()
        for line in _scaffold_section().splitlines()
        if line.strip().startswith("- ")
    ]
    prose = [b for b in bullets if not is_repo_relative_path(b)]
    assert not prose, (
        f"the scaffold emits prose where the gate reads repo-relative paths: {prose}"
    )


def test_c014_unit_004_the_empty_subsections_say_how_to_fill_them():
    """The empty form is an instruction, not a blank — and not a placeholder string."""
    from atdd.coach.commands.issue_template import PLACEHOLDER_STRINGS
    from atdd.planner.commands.author_issue import EMPTY_DECLARATION

    section = _scaffold_section()
    assert section.count(EMPTY_DECLARATION) == 3, (
        "each of Created / Modified / Deleted must say it has nothing yet, and "
        "how to derive it"
    )
    leaked = [p for p in PLACEHOLDER_STRINGS if p in EMPTY_DECLARATION]
    assert not leaked, (
        "the empty form must not be an unfilled-template placeholder the E019 "
        f"gate rejects: {leaked}"
    )


def test_c014_unit_004_the_scaffold_yields_no_resolve_violation():
    """The section the toolkit ships cannot fail the resolve rule on emission."""
    from atdd.coach.utils.artifact_claims import (
        RULE_CLAIMS_RESOLVE,
        check_artifact_claims,
    )

    report = check_artifact_claims(
        _scaffold_artifacts(), resolves=_always_resolves, issue_number=1726,
    )

    unresolvable = [v for v in report.violations if v.rule_id == RULE_CLAIMS_RESOLVE]
    assert not unresolvable, (
        "the authored body still fails the gate it is destined for: "
        f"{[v.detail for v in unresolvable]}"
    )


def test_c014_unit_004_the_empty_form_is_still_a_completeness_violation():
    """An honest empty is not a free pass — the placeholder does not buy exemption."""
    from atdd.coach.utils.artifact_claims import (
        RULE_MUST_BE_DECLARED,
        check_artifact_claims,
    )

    report = check_artifact_claims(
        _scaffold_artifacts(), resolves=_always_resolves, issue_number=1726,
    )

    assert [v.rule_id for v in report.violations] == [RULE_MUST_BE_DECLARED]
