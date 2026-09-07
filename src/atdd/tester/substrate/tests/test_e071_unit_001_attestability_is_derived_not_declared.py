# URN: test:govern-lifecycle:live-smoke-attestability:E071-UNIT-001-attestability-is-derived-not-declared
# Acceptance: acc:govern-lifecycle:E071-UNIT-001-attestability-is-derived-not-declared
# WMBT: wmbt:govern-lifecycle:E071
# Phase: RED
# Layer: unit
# Assertion: behavioral
# Runtime: python
"""E071-UNIT-001 — the class is computed from train membership and test layer.

    No input to `classify` is written by the author of the acceptance being
    classified.

#1609 required authors to declare `execution_kind`; that is self-attestation,
and its own feature file escaped its own C011 by declaring
`components.backend.integration: count: 0`. This classifier consumes only
train membership (gate-enforced: the phase machine refuses to leave PLANNED
without a train) and the anchored test's `# Layer:` header.
"""
from __future__ import annotations

from pathlib import Path

from atdd.tester.substrate.attestability import (
    CAN_ATTEST,
    NEVER_ATTESTABLE,
    SHOULD_DECLARE,
    UNRESOLVED,
    classify,
    train_wagons,
)

_URN = "acc:govern-lifecycle:E071-SMOKE-001"
_IN_TRAIN = {"govern-lifecycle"}
_T = Path("src/atdd/x/test_x.py")


def test_smoke_layer_test_can_attest_today() -> None:
    got = classify(_URN, _IN_TRAIN, {_URN: [_T]}, {_T: "smoke"})
    assert got is not None and got.klass == CAN_ATTEST


def test_in_train_but_anchored_by_integration_should_declare() -> None:
    """The 309-of-318 case: a SMOKE acceptance discharged by a non-smoke test."""
    got = classify(_URN, _IN_TRAIN, {_URN: [_T]}, {_T: "integration"})
    assert got is not None and got.klass == SHOULD_DECLARE
    assert "claims SMOKE, is not one" in got.reason


def test_wagon_in_no_train_is_never_attestable() -> None:
    got = classify(_URN, set(), {_URN: [_T]}, {_T: "integration"})
    assert got is not None and got.klass == NEVER_ATTESTABLE


def test_unanchored_acceptance_is_unresolved_never_coverage() -> None:
    """`unresolved` routes to adjudication; it must never read as attestable."""
    got = classify(_URN, _IN_TRAIN, {}, {})
    assert got is not None and got.klass == UNRESOLVED
    assert got.klass not in (CAN_ATTEST,)


def test_test_without_layer_header_is_unresolved_not_assumed() -> None:
    got = classify(_URN, _IN_TRAIN, {_URN: [_T]}, {_T: None})
    assert got is not None and got.klass == UNRESOLVED


def test_non_smoke_urn_is_not_classified() -> None:
    assert classify("acc:govern-lifecycle:E071-UNIT-001", _IN_TRAIN, {}, {}) is None


def test_train_wagons_unions_across_groups_and_categories() -> None:
    doc = {"trains": {
        "grp-a": {"nominal": [{"train_id": "t1", "wagons": ["w1", "w2"]}]},
        "grp-b": {"nominal": [{"train_id": "t2", "wagons": ["w2", "w3"]}]},
    }}
    assert train_wagons(doc) == {"w1", "w2", "w3"}


def test_train_wagons_tolerates_a_malformed_document() -> None:
    assert train_wagons({}) == set()
    assert train_wagons({"trains": {"g": {"n": [None, "junk"]}}}) == set()
