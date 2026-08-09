# URN: test:govern-registry:govern-registry:E004-UNIT-002-every-broken-link-refuses-under-its-own-name
# Acceptance: acc:govern-registry:E004-UNIT-002-every-broken-link-refuses-under-its-own-name
# WMBT: wmbt:govern-registry:E004
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Each link of the proof chain, broken alone against an otherwise complete realization, refuses under its OWN named basis — a predicate nobody has shown can fail is not a predicate that passed.
"""acc:govern-registry:E004-UNIT-002 — the fault matrix.

A predicate nobody has shown can fail is exactly the theatre program #1772
exists to prevent, so the faults ship with the predicate rather than after it.
#1207 set the bar for an alternate proof: clean baseline PLUS fault injection.

Each case starts from ONE complete realization and breaks exactly ONE link, so a
refusal cannot be credited to an accidental second difference. Two properties are
asserted, and the second is the one that has teeth:

  * every arm refuses (none discharges, none raises); and
  * every arm refuses under its OWN basis, and together they cover the refusal
    vocabulary exactly — so no arm is quietly served by another arm's name, and
    no basis is declared that nothing can produce.

Acquisition failures are held apart from refusals throughout: a lock or manifest
that cannot be READ is not a lock that says no. Collapsing the two would let an
unreadable substrate report as a clean refusal, which is the shape #1716/#1725
forbid.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators._bound_realization import (
    NOT_APPLICABLE_BASES,
    REFUSAL_BASES,
    UNOBSERVABLE,
    UNOBSERVABLE_BASES,
    BoundRealizationResolver,
)
from atdd.coach.validators.tests import _e004_substrate as fx

pytestmark = [pytest.mark.coach]


#: One entry per link of the chain: (basis, mutator). The basis is the name the
#: refusal MUST carry — asserting the name, not merely the refusal, is what stops
#: one broken link from being reported as another.
FAULTS = [
    ("stale-substrate-digest", fx.break_digest),
    ("no-lock-entry", fx.drop_lock_entry),
    ("not-bound", fx.set_disposition),
    ("ambiguous-lock-selection", fx.duplicate_lock_entry),
    ("no-implementation-manifest", fx.drop_manifest),
    ("ambiguous-implementation-selection", fx.duplicate_manifest),
    ("ambiguous-convention-ownership", fx.add_second_owner),
    ("realizes-mismatch", fx.drop_realizes),
    ("emits-mismatch", fx.drop_emits),
    ("ownership-not-emitted", fx.realizes_not_emitted),
    ("no-report-channel", fx.drop_report_field),
    ("unresolvable-report", fx.unlink_report_file),
    ("provider-unrunnable", fx.drop_provider_cli),
    ("path-b-not-blocking", lambda root: fx.set_path_b_blocking(root, blocking=False)),
]


@pytest.mark.parametrize("basis,inject", FAULTS, ids=[f[0] for f in FAULTS])
def test_each_broken_link_refuses_under_its_own_basis(tmp_path, basis, inject):
    root = fx.build_complete(tmp_path)
    # Sanity: the baseline this fault is injected against genuinely proves.
    assert BoundRealizationResolver.for_repo(root).discharges(fx.RULE_ID) is True

    inject(root)
    proof = BoundRealizationResolver.for_repo(root).proof_for(fx.RULE_ID)

    assert proof.discharges is False, f"{basis} must refuse the discharge"
    assert proof.outcome == "fail"
    assert proof.basis == basis
    # Attribution lives on the record, so every refusal is traceable to its rule
    # however the caller renders it.
    assert proof.rule_id == fx.RULE_ID
    # A refusal an operator cannot act on is only marginally better than the
    # vacuous pass it replaces. The detail must point at a CONCRETE artefact of
    # this substrate — the rule, the implementation, or a path — not merely
    # restate that the rule is unproven.
    assert any(
        token in proof.detail for token in (fx.RULE_ID, fx.IMPL_ID, str(root))
    ), f"{basis} refusal names no concrete artefact: {proof.detail!r}"


def test_the_matrix_covers_the_refusal_vocabulary_exactly(tmp_path):
    """No declared refusal is unreachable, and no arm borrows another's name."""
    covered = {basis for basis, _ in FAULTS}

    assert covered == set(REFUSAL_BASES), (
        "every declared refusal needs an arm that produces it, and every arm "
        "needs a declared name: "
        f"unproduced={sorted(set(REFUSAL_BASES) - covered)} "
        f"undeclared={sorted(covered - set(REFUSAL_BASES))}"
    )
    assert len(covered) == len(FAULTS), "two arms share a basis"


@pytest.mark.parametrize(
    "basis,inject",
    [
        ("unreadable-lock", fx.corrupt_lock),
        ("unreadable-implementation-manifest", fx.corrupt_manifest),
    ],
)
def test_unreadable_evidence_is_an_acquisition_failure_not_a_refusal(
    tmp_path, basis, inject
):
    """Evidence that cannot be read stays DATA — named, reportable, not clean."""
    root = fx.build_complete(tmp_path)
    inject(root)

    proof = BoundRealizationResolver.for_repo(root).proof_for(fx.RULE_ID)

    assert proof.outcome == UNOBSERVABLE
    assert proof.basis == basis
    assert proof.discharges is False, "could-not-check never discharges"
    assert basis not in REFUSAL_BASES, (
        "an unreadable substrate is not a substrate that said no; keeping the "
        "two vocabularies disjoint is what stops the first being reported as "
        "the second"
    )


def test_the_three_refusing_vocabularies_are_disjoint():
    """A basis means one thing. Overlap would make the outcome ambiguous."""
    refusals, unobservable, na = (
        set(REFUSAL_BASES),
        set(UNOBSERVABLE_BASES),
        set(NOT_APPLICABLE_BASES),
    )
    assert refusals & unobservable == set()
    assert refusals & na == set()
    assert unobservable & na == set()


def test_an_alias_shaped_lock_entry_does_not_resolve_the_rule(tmp_path):
    """``convention_id == rule_id`` is asserted, never inferred.

    ``binding-lock.schema.json`` types ``convention_id`` as a free
    ``minLength: 1`` string with no rule-id pattern, so the identity the whole
    predicate rests on is empirical rather than guaranteed. A near-miss — a
    prefix, a case-fold, a legacy alias — must therefore NOT resolve.
    """
    for near_miss in (
        fx.RULE_ID.upper(),
        fx.RULE_ID.rsplit(".", 1)[0],
        fx.RULE_ID + "-legacy",
        "CODER-FIXTURE-BOUND-RULE",
    ):
        root = fx.build_complete(tmp_path / near_miss.replace(".", "_"))
        lock = fx.read_lock(root)
        lock["conventions"][0]["convention_id"] = near_miss
        fx.write_lock(root, lock)

        proof = BoundRealizationResolver.for_repo(root).proof_for(fx.RULE_ID)

        assert proof.discharges is False, f"{near_miss!r} must not resolve {fx.RULE_ID!r}"
        assert proof.basis == "no-lock-entry"
