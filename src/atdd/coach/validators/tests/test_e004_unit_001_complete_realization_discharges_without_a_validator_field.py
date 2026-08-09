# URN: test:govern-registry:govern-registry:E004-UNIT-001-complete-realization-discharges-without-a-validator-field
# Acceptance: acc:govern-registry:E004-UNIT-001-complete-realization-discharges-without-a-validator-field
# WMBT: wmbt:govern-registry:E004
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A provider-realized enforced rule discharges reverse coherence with no validator: field and no placeholder, because the proof is consulted ahead of both rejection branches.
"""acc:govern-registry:E004-UNIT-001 — the discharge, and where it fires.

The claim under test is not merely "a complete realization proves a rule". It is
that the proof is consulted EARLY ENOUGH to matter: an enforced rule carrying no
``validator:`` field at all, and no placeholder value, passes reverse coherence.

That distinction is the whole issue. Before #1773 such a rule was rejected at the
``not validator_field`` branch, strictly before any point where a lock could be
consulted — so a discharge placed after it would be unreachable, and a
provider-proven rule would have had to invent a ``validator:`` value to get far
enough to be discharged. A discharge that required a declaration would not be a
third proof; it would be a new declaration wearing one.

The third assertion is what keeps this test honest: the SAME rule, with the SAME
registry, against a repository with no substrate, still violates. Without it, a
green here would be indistinguishable from a validator that simply stopped
checking.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.rule_id_registry import RuleMetadata
from atdd.coach.validators import test_rule_validator_binding as reverse
from atdd.coach.validators._bound_realization import (
    PROVEN,
    PROVEN_BASIS,
    BoundRealizationResolver,
)
from atdd.coach.validators.tests import _e004_substrate as fx

pytestmark = [pytest.mark.coach]


def _registry(disposition: str = "strict", validator=None) -> dict:
    """A registry of exactly one enforced rule, with no validator: by default."""
    return {
        fx.RULE_ID: RuleMetadata(
            rule_id=fx.RULE_ID,
            convention_path=Path("plan/fixture/fixture.convention.yaml"),
            severity=3,
            description="fixture rule realized by a bound provider",
            disposition=disposition,
            validator=validator,
        )
    }


def _violations_over(monkeypatch, root: Path | None, registry: dict) -> list:
    """Run reverse coherence against ``registry`` and the substrate at ``root``."""
    monkeypatch.setattr(reverse, "build_registry", lambda: registry)
    monkeypatch.setattr(
        reverse,
        "_realization_resolver",
        lambda: None if root is None else BoundRealizationResolver.for_repo(root),
    )
    return reverse._build_violations()


def test_complete_realization_is_proven(tmp_path):
    """The chain resolves, and says so on the one basis that discharges."""
    root = fx.build_complete(tmp_path)

    proof = BoundRealizationResolver.for_repo(root).proof_for(fx.RULE_ID)

    assert proof.outcome == PROVEN
    assert proof.basis == PROVEN_BASIS
    assert proof.discharges is True
    # The proof carries WHICH realization proved it — a discharge that could not
    # name its implementation would be unauditable.
    assert proof.implementation_id == fx.IMPL_ID
    assert proof.workspace_id == fx.WORKSPACE_ID
    assert proof.manifest_path == fx.manifest_path(root)


def test_enforced_rule_with_no_validator_field_passes_reverse_coherence(
    tmp_path, monkeypatch
):
    """No ``validator:`` field, no placeholder — and no violation."""
    root = fx.build_complete(tmp_path)
    registry = _registry()
    assert registry[fx.RULE_ID].validator is None, "the premise: nothing is declared"

    violations = _violations_over(monkeypatch, root, registry)

    assert violations == [], (
        "an enforced rule proven by a complete bound realization must pass "
        "reverse coherence without declaring a validator: "
        f"got {[v.detail for v in violations]}"
    )


def test_the_same_rule_without_a_substrate_still_violates(tmp_path, monkeypatch):
    """The discharge came from the realization, not from the rule's own say-so."""
    bare = tmp_path / "no_substrate"
    bare.mkdir()
    registry = _registry()

    violations = _violations_over(monkeypatch, bare, registry)

    assert len(violations) == 1, "an unproven enforced rule must still be caught"
    detail = violations[0].detail
    assert "declares no validator: field" in detail
    # And it says why the provider route did not carry it either, rather than
    # leaving the operator with "declare a validator" and no further information.
    assert "bound-realization proof: no-local-substrate" in detail


def test_discharge_is_evaluated_before_the_unresolvable_validator_branch(
    tmp_path, monkeypatch
):
    """Placement, stated as behaviour rather than as a line number.

    A rule naming a validator that cannot be resolved at all is rejected by
    ``resolve_validator`` — unless the discharge has already fired. This is the
    second of the two branches the proof must precede.
    """
    root = fx.build_complete(tmp_path)
    registry = _registry(validator="no_such_module_anywhere::no_such_function")

    assert _violations_over(monkeypatch, root, registry) == []

    # …and with no substrate, that same unresolvable validator IS reported, so
    # the branch is intact and merely preceded.
    bare = tmp_path / "bare"
    bare.mkdir()
    violations = _violations_over(monkeypatch, bare, registry)
    assert len(violations) == 1
    assert "could not be resolved" in violations[0].detail
