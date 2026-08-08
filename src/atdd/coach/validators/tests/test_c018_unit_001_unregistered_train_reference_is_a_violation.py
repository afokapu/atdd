# URN: test:govern-lifecycle:bind-issue-train:C018-UNIT-001-unregistered-train-reference-is-a-violation
# Acceptance: acc:govern-lifecycle:C018-UNIT-001-unregistered-train-reference-is-a-violation
# WMBT: wmbt:govern-lifecycle:C018
# Phase: GREEN
# Layer: domain
# Runtime: python
# Assertion: behavioral
# Purpose: The scan distinguishes the shapes a train reference can fail in — placeholder, unregistered identity, resolvable alias — and reports each unresolvable one against the reference rule.
"""GREEN test for acc:govern-lifecycle:C018-UNIT-001-unregistered-train-reference-is-a-violation.

wagon: govern-lifecycle | feature: bind-issue-train | WMBT: wmbt:govern-lifecycle:C018

`atdd update <N> --train` wrote any string at all — proven, it accepted
``train:bogus:does-not-exist`` — because no convention node said a train must
resolve, so nothing read the registry back. This holds the scan to the three
distinct answers a reference can earn, and to the one it must NOT give: an issue
that names no train is not in violation, because a train is optional for the
issue types that do not require one.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators.issue_train_binding_scanner import scan_train_references

from ._bind_issue_train_helpers import (
    ABSENT_TRAIN,
    CONSUMER_TRAIN,
    CONSUMER_TRAIN_LEGACY,
    PLACEHOLDER_TRAIN,
    control_root,
    issue_record,
    rule_ids,
    write_consumer_plan_tree,
)

_REFERENCE_RULE = "coach.train-reference.resolves-to-registered-train"


@pytest.fixture()
def repo(tmp_path):
    root = control_root(tmp_path)
    write_consumer_plan_tree(root)
    return root


def _scan(repo, *records):
    return scan_train_references(list(records), plan_root=repo)


def test_a_registered_canonical_train_is_not_reported(repo) -> None:
    violations = _scan(repo, issue_record(1, CONSUMER_TRAIN))
    assert violations == [], (
        f"a train the registry declares was reported as unresolvable: "
        f"{[v.detail for v in violations]}"
    )


def test_a_resolvable_alias_is_not_reported(repo) -> None:
    """A legacy id still resolves through the alias map (#1421).

    The reader this replaced knew only exact registry entries and loose flat
    stems, so it rejected exactly this — and the alias forms are 27 of the live
    corpus's train references.
    """
    violations = _scan(repo, issue_record(2, CONSUMER_TRAIN_LEGACY))
    assert violations == [], (
        f"a legacy id the alias map resolves was reported as unresolvable: "
        f"{[v.detail for v in violations]}"
    )


def test_the_alias_verdict_names_the_canonical_train_it_resolved_to(repo) -> None:
    """A reader must not be left holding the legacy spelling."""
    from atdd.planner.commands.train_binding import resolve_train

    verdict = resolve_train(CONSUMER_TRAIN_LEGACY, repo)

    assert verdict.resolved
    assert verdict.train_id == CONSUMER_TRAIN, (
        f"the alias resolved but reported train_id={verdict.train_id!r} instead of "
        f"the canonical {CONSUMER_TRAIN!r} it names"
    )


def test_a_well_formed_but_unregistered_train_is_reported(repo) -> None:
    violations = _scan(repo, issue_record(3, ABSENT_TRAIN))

    assert rule_ids(violations) == [_REFERENCE_RULE], (
        f"an unregistered train produced {rule_ids(violations)}"
    )
    detail = violations[0].detail
    assert "plan/_trains.yaml" in detail, (
        f"the violation does not name the registry it consulted: {detail!r}"
    )
    assert CONSUMER_TRAIN in detail, (
        "the violation does not list a registered train that WOULD have resolved, "
        f"so the reader must re-derive the registry by hand: {detail!r}"
    )


def test_a_placeholder_is_reported_as_the_wrong_shape_not_merely_absent(repo) -> None:
    """"TBD" is what 11 live work items actually carry.

    Reporting it as "not registered" would send an operator looking for a train
    called TBD. The two failures are different and must read differently.
    """
    violations = _scan(repo, issue_record(4, PLACEHOLDER_TRAIN))

    assert rule_ids(violations) == [_REFERENCE_RULE]
    detail = violations[0].detail
    assert "not a train identity" in detail, (
        f"a placeholder was not reported as the wrong shape: {detail!r}"
    )
    assert "train:<subject>:<slug>" in detail, (
        f"the violation does not name the shape that would be accepted: {detail!r}"
    )


def test_an_issue_with_no_train_is_not_reported(repo) -> None:
    """A train is optional for the issue types that do not require one.

    This rule governs a reference that WAS set. Reporting the 481 live work items
    that declare no train would drown the 16 that declare a broken one.
    """
    violations = _scan(repo, issue_record(5, None), issue_record(6, ""))
    assert violations == [], (
        f"an issue carrying no train was reported: {[v.detail for v in violations]}"
    )


def test_a_terminal_issue_is_not_reported(repo) -> None:
    """Repairing the lineage of shipped work changes nothing actionable."""
    violations = _scan(
        repo,
        issue_record(7, ABSENT_TRAIN, status="COMPLETE"),
        issue_record(8, ABSENT_TRAIN, status="OBSOLETE"),
    )
    assert violations == [], (
        f"a terminal issue was reported: {[v.location for v in violations]}"
    )


def test_every_violation_is_actionable_without_re_deriving_its_issue(repo) -> None:
    """rule_id + a location naming the issue, or the report cannot be acted on."""
    violations = _scan(repo, issue_record(9, ABSENT_TRAIN))

    assert len(violations) == 1
    violation = violations[0]
    assert violation.rule_id == _REFERENCE_RULE
    assert violation.severity, "the violation carries no severity from its rule"
    assert "9" in violation.location, (
        f"the location does not name the issue it came from: {violation.location!r}"
    )
