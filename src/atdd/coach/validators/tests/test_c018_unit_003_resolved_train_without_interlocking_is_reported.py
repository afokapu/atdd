# URN: test:govern-lifecycle:bind-issue-train:C018-UNIT-003-resolved-train-without-interlocking-is-reported
# Acceptance: acc:govern-lifecycle:C018-UNIT-003-resolved-train-without-interlocking-is-reported
# WMBT: wmbt:govern-lifecycle:C018
# Phase: GREEN
# Layer: domain
# Runtime: python
# Assertion: behavioral
# Purpose: The interlocking assertion is a separate rule with its own id and disposition, so a resolved-but-unrouted train is reported without blocking the build the reference rule shares.
"""GREEN test for acc:govern-lifecycle:C018-UNIT-003-resolved-train-without-interlocking-is-reported.

wagon: govern-lifecycle | feature: bind-issue-train | WMBT: wmbt:govern-lifecycle:C018

Decision 2 of #1590, ruled YES by the operator on 2026-08-03: the validator ALSO
requires the resolved train's interlocking to be defined. It is held as its own
rule rather than a second assertion under the reference rule's id, because the
disposition gate reads disposition PER rule_id and the measured populations are
two orders of magnitude apart — 16 unresolvable references against 148 unrouted
trains on ff55607b.

Note what a route may name its train BY. atdd's own two interlocking artifacts do
it both ways: ``collaborate-through-projection`` carries ``train_id`` in the typed
spelling, ``enforce-extension-conventions`` carries the legacy one, and both carry
``train_path``. A matcher honouring one spelling would read the other as a
missing interlocking.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.rule_id_registry import build_registry
from atdd.coach.validators.issue_train_binding_scanner import scan_train_references

from ._bind_issue_train_helpers import (
    ABSENT_TRAIN,
    CONSUMER_TRAIN,
    CONSUMER_TRAIN_UNROUTED,
    control_root,
    issue_record,
    rule_ids,
    write_consumer_plan_tree,
)

_REFERENCE_RULE = "coach.train-reference.resolves-to-registered-train"
_INTERLOCKING_RULE = "coach.train-reference.resolved-train-has-interlocking"


@pytest.fixture()
def repo(tmp_path):
    """Two registered trains; exactly one routed, by path."""
    root = control_root(tmp_path)
    write_consumer_plan_tree(root, routed=(CONSUMER_TRAIN,), route_by_path=True)
    return root


def test_a_routed_train_produces_no_interlocking_violation(repo) -> None:
    violations = scan_train_references([issue_record(1, CONSUMER_TRAIN)], plan_root=repo)
    assert violations == [], (
        f"a train an interlocking routes through was reported as unrouted: "
        f"{[v.detail for v in violations]}"
    )


def test_an_unrouted_train_is_reported_under_the_interlocking_rule(repo) -> None:
    """The id matters: it is what decides which disposition governs the verdict."""
    violations = scan_train_references(
        [issue_record(2, CONSUMER_TRAIN_UNROUTED)], plan_root=repo
    )

    assert rule_ids(violations) == [_INTERLOCKING_RULE], (
        f"an unrouted train was reported under {rule_ids(violations)} instead of "
        f"the interlocking rule — the reference itself is fine"
    )
    assert CONSUMER_TRAIN_UNROUTED in violations[0].detail
    assert "interlocking" in violations[0].detail


def test_a_route_naming_its_train_by_train_id_also_counts_as_coverage(tmp_path) -> None:
    """A registry spelling difference must not read as a missing interlocking."""
    root = control_root(tmp_path / "by-id")
    write_consumer_plan_tree(root, routed=(CONSUMER_TRAIN,), route_by_path=False)

    violations = scan_train_references([issue_record(3, CONSUMER_TRAIN)], plan_root=root)

    assert violations == [], (
        "a route naming its train by train_id was not counted as coverage: "
        f"{[v.detail for v in violations]}"
    )


def test_an_unresolvable_reference_yields_no_interlocking_violation(repo) -> None:
    """One defect, one violation.

    There is no resolved train whose interlocking could be missing, so reporting
    both rules would double-count the same broken reference and inflate a
    baseline the other rule is trying to ratchet down.
    """
    violations = scan_train_references([issue_record(4, ABSENT_TRAIN)], plan_root=repo)

    assert rule_ids(violations) == [_REFERENCE_RULE], (
        f"an unresolvable reference produced {rule_ids(violations)}"
    )


def test_the_two_rules_are_declared_with_their_own_dispositions() -> None:
    """Read from the convention registry, never asserted as a literal verdict.

    The gate takes severity and disposition from the node; a test asserting the
    outcome directly would pin policy in code where the convention owns it.
    """
    registry = build_registry()

    for rule_id in (_REFERENCE_RULE, _INTERLOCKING_RULE):
        assert rule_id in registry, f"{rule_id} is declared by no convention"
        assert registry[rule_id].disposition in {
            "strict", "advisory", "suppress-and-clean",
        }, f"{rule_id} carries no enforceable disposition"
        assert registry[rule_id].validator, (
            f"{rule_id} names no validator, so reverse coherence cannot bind it"
        )

    assert registry[_REFERENCE_RULE].validator != registry[_INTERLOCKING_RULE].validator, (
        "both rules name the same validator FUNCTION, so one disposition would "
        "govern both verdicts — which is the collapse this decomposition avoids"
    )


def test_both_rules_can_be_reported_from_one_scan_without_merging(repo) -> None:
    """A mixed corpus produces one violation per defect, each under its own rule."""
    violations = scan_train_references(
        [
            issue_record(5, CONSUMER_TRAIN),           # clean
            issue_record(6, CONSUMER_TRAIN_UNROUTED),  # unrouted
            issue_record(7, ABSENT_TRAIN),             # unresolvable
        ],
        plan_root=repo,
    )

    assert sorted(rule_ids(violations)) == sorted([_INTERLOCKING_RULE, _REFERENCE_RULE]), (
        f"the scan did not keep the two failure modes apart: {rule_ids(violations)}"
    )
