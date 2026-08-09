# URN: test:govern-registry:govern-registry:E004-UNIT-004-not-applicable-grants-no-discharge-and-counts-as-nothing
# Acceptance: acc:govern-registry:E004-UNIT-004-not-applicable-grants-no-discharge-and-counts-as-nothing
# WMBT: wmbt:govern-registry:E004
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A substrate-less consumer's provider-proof branch concludes NOT_APPLICABLE without erroring, grants NO discharge, and is never counted as verified enforcement.
"""acc:govern-registry:E004-UNIT-004 — the branch that is owed nothing.

``NOT_APPLICABLE`` is the member of the vocabulary that carries the risk of
re-collapsing the distinction it was created to make, so it is held precisely
here. A consumer with no local substrate is owed no provider proof: the branch
*did* observe successfully and correctly concluded there is no obligation. That
is not "I could not look", and it is emphatically not "the rule is proven".

Two halves, and shipping only the first is the failure mode:

  * the branch does not error — absence of an optional layout is not a fault; and
  * the branch grants NO discharge — the enforced rule still fails reverse
    coherence unless a literal binding or a convention variant supplies proof.

The third guard is against counting: a ``NOT_APPLICABLE`` result must never be
tallied or described as verified enforcement (#1747). ``decision.py``'s
``passed_checks`` already excludes it, and ``approve_command.py`` records that
"a reported NOT_APPLICABLE verified nothing, and a bare ✓ reads identically".
This issue must not reintroduce the collapse from the other side.
"""
from __future__ import annotations

import enum
from pathlib import Path

import pytest

from atdd.coach.utils.rule_id_registry import RuleMetadata
from atdd.coach.validators import test_rule_validator_binding as reverse
from atdd.coach.validators import _bound_realization as br
from atdd.coach.validators.tests import _e004_substrate as fx

pytestmark = [pytest.mark.coach]


@pytest.fixture()
def unconfigured(tmp_path):
    """A repository with no ``.atdd`` at all — the zero-substrate consumer."""
    root = tmp_path / "consumer"
    (root / "src").mkdir(parents=True)
    return root


def test_the_branch_concludes_not_applicable_without_erroring(unconfigured):
    proof = br.BoundRealizationResolver.for_repo(unconfigured).proof_for(fx.RULE_ID)

    assert proof.outcome == br.NOT_APPLICABLE
    assert proof.basis == "no-local-substrate"
    assert "grants NO discharge" in proof.detail


def test_not_applicable_grants_no_discharge(unconfigured, monkeypatch):
    """The second half — the one that is easy to ship without."""
    proof = br.BoundRealizationResolver.for_repo(unconfigured).proof_for(fx.RULE_ID)
    assert proof.discharges is False

    registry = {
        fx.RULE_ID: RuleMetadata(
            rule_id=fx.RULE_ID,
            convention_path=Path("plan/fixture/fixture.convention.yaml"),
            disposition="strict",
        )
    }
    monkeypatch.setattr(reverse, "build_registry", lambda: registry)
    monkeypatch.setattr(
        reverse,
        "_realization_resolver",
        lambda: br.BoundRealizationResolver.for_repo(unconfigured),
    )

    violations = reverse._build_violations()
    assert len(violations) == 1, (
        "an enforced rule in a substrate-less consumer must still fail reverse "
        "coherence — NOT_APPLICABLE may permit progress, never verification"
    )


def test_not_applicable_is_never_counted_as_verified(unconfigured):
    """`verified` is the predicate a report must consult before writing 'proven'."""
    na = br.BoundRealizationResolver.for_repo(unconfigured).proof_for(fx.RULE_ID)
    assert na.verified is False

    proven = br.BoundRealizationResolver.for_repo(
        fx.build_complete(unconfigured.parent / "configured")
    ).proof_for(fx.RULE_ID)
    assert proven.verified is True

    # Counting a mixed set must yield ONE, not two.
    assert sum(p.verified for p in (na, proven)) == 1


def test_the_toolkit_lock_is_never_borrowed_for_a_consumer(unconfigured):
    """The false green #1772 Decision 13 measured, refused at its source.

    ``enforce.runner.resolve_substrate_home`` deliberately falls back to the
    toolkit install so an un-bound consumer still gets the toolkit's bound rules
    enforced over its code. That is right for enforcement and wrong for proof:
    borrowing it here would manufacture 62 discharges for rules the consumer
    never configured.
    """
    from atdd.enforce.runner import _toolkit_root, resolve_substrate_home

    borrowed = resolve_substrate_home(unconfigured)
    assert borrowed == _toolkit_root(), "the premise: enforce does fall back"

    resolver = br.BoundRealizationResolver.for_repo(unconfigured)
    assert resolver.substrate_home == unconfigured
    assert not resolver.lock_path.is_file()

    # Every rule the toolkit's own lock declares bound resolves to NOTHING here.
    toolkit_lock = br.BoundRealizationResolver.for_repo(_toolkit_root())
    import yaml

    bound_ids = [
        c["convention_id"]
        for c in (yaml.safe_load(toolkit_lock.lock_path.read_text()) or {})["conventions"]
    ]
    assert bound_ids, "the premise: the toolkit really does ship a populated lock"
    for rule_id in bound_ids:
        proof = resolver.proof_for(rule_id)
        assert proof.outcome == br.NOT_APPLICABLE
        assert proof.discharges is False


def test_the_vocabulary_is_closed_and_every_basis_means_one_outcome():
    """A basis added later cannot acquire an outcome by omission."""
    assert set(br.BASIS_OUTCOME.values()) <= set(br.OUTCOMES)
    declared = (
        {br.PROVEN_BASIS}
        | set(br.REFUSAL_BASES)
        | set(br.UNOBSERVABLE_BASES)
        | set(br.NOT_APPLICABLE_BASES)
    )
    assert set(br.BASIS_OUTCOME) == declared, "BASIS_OUTCOME must be total over the bases"
    assert br.BASIS_OUTCOME[br.PROVEN_BASIS] == br.PROVEN
    assert len(set(br.OUTCOMES)) == 4


def test_a_proof_whose_basis_and_outcome_disagree_is_refused():
    """Two representations of one fact must not be silently reconciled."""
    with pytest.raises(ValueError, match="not in the closed vocabulary"):
        br.BoundRealizationProof(
            rule_id=fx.RULE_ID, outcome=br.PROVEN, basis="invented-basis", detail="x"
        )

    with pytest.raises(ValueError, match="must not disagree"):
        br.BoundRealizationProof(
            rule_id=fx.RULE_ID,
            outcome=br.PROVEN,  # claims proven…
            basis="no-lock-entry",  # …on a basis that means refused
            detail="x",
        )


def test_only_proven_discharges_across_the_whole_vocabulary():
    """Stated once, over every outcome, so no future outcome defaults to yes."""
    for basis, outcome in br.BASIS_OUTCOME.items():
        proof = br.BoundRealizationProof(
            rule_id=fx.RULE_ID, outcome=outcome, basis=basis, detail="x"
        )
        assert proof.discharges is (outcome == br.PROVEN)
        assert proof.verified is (outcome == br.PROVEN)


def test_no_second_verdict_enum_is_defined():
    """#1772 Decisions 16-18: the meanings are reused; no new type is authored."""
    enums = [
        name
        for name, obj in vars(br).items()
        if isinstance(obj, type) and issubclass(obj, enum.Enum)
    ]
    assert enums == [], (
        f"the proof module defines enum(s) {enums} — #1719 already shipped the "
        f"verdict vocabulary; a second enum for the same question is the "
        f"duplication this program exists to oppose"
    )
