# URN: test:author-atdd-substrate:author-issue-body:C014-UNIT-001-empty-declaration-is-a-violation
# Acceptance: acc:author-atdd-substrate:C014-UNIT-001-empty-declaration-is-a-violation
# WMBT: wmbt:author-atdd-substrate:C014
# Phase: RED
# Layer: application
"""C014-UNIT-001 — an empty `## Artifacts` declaration is a violation, not an exemption.

Today both enforcers carry their own copy of the same escape::

    total = sum(len(v) for v in artifacts.values())
    if total == 0:
        continue                                   # the validator skips the issue
        return True, ["  No artifacts declared"]   # the runtime gate passes it

So an issue that declares nothing is exempt from the COMPLETE gate entirely,
while one that declares accurately has every entry checked against git. This
fails until ONE shared checker — bound to the convention rather than inventing
its own policy — reports the empty declaration as a violation (GREEN).

"No artifacts declared" is a determinable answer (the empty set), not an
unobservable one, so it resolves to a violation rather than to the third
``GateCheckResult`` verdict #1719 introduces.
"""
from __future__ import annotations

import pytest


def _always_resolves(kind: str, path: str) -> bool:
    """A git probe that confirms every claim, so only the policy is under test."""
    return True


def test_c014_unit_001_empty_declaration_is_a_violation():
    from atdd.coach.utils.artifact_claims import (
        RULE_MUST_BE_DECLARED,
        check_artifact_claims,
    )

    report = check_artifact_claims(
        {"created": [], "modified": [], "deleted": []},
        resolves=_always_resolves,
        issue_number=1726,
    )

    assert report.violations, (
        "an issue declaring no artifacts must be reported as a violation, "
        "not skipped — `total == 0` is the empty set, not an exemption"
    )
    assert [v.rule_id for v in report.violations] == [RULE_MUST_BE_DECLARED], (
        f"the empty declaration must be attributed to {RULE_MUST_BE_DECLARED}, "
        f"got {[v.rule_id for v in report.violations]}"
    )


def test_c014_unit_001_an_absent_section_is_the_same_violation():
    """A body with the `## Artifacts` section deleted parses to the same empty set.

    Deleting the section was the cheapest path to green under the old policy.
    It must not be a cheaper path than filling it in.
    """
    from atdd.coach.commands.issue import IssueManager
    from atdd.coach.utils.artifact_claims import (
        RULE_MUST_BE_DECLARED,
        check_artifact_claims,
    )

    parsed = IssueManager._parse_artifacts("# An issue with no Artifacts section\n")
    report = check_artifact_claims(parsed, resolves=_always_resolves, issue_number=1726)

    assert [v.rule_id for v in report.violations] == [RULE_MUST_BE_DECLARED]


def test_c014_unit_001_the_rule_is_declared_in_a_convention():
    """The checker answers from a rule the convention declares (SPEC-COACH-RULEID-0007)."""
    from atdd.coach.utils.artifact_claims import RULE_MUST_BE_DECLARED
    from atdd.coach.utils.rule_binding import RuleNotInRegistryError, bind_rule

    try:
        meta = bind_rule(RULE_MUST_BE_DECLARED)
    except RuleNotInRegistryError as exc:  # pragma: no cover — the RED failure
        pytest.fail(
            f"{RULE_MUST_BE_DECLARED!r} is not declared in any convention: {exc}"
        )
    assert meta.rule_id == RULE_MUST_BE_DECLARED
    assert meta.severity, "the rule must carry a severity the gate can route on"
