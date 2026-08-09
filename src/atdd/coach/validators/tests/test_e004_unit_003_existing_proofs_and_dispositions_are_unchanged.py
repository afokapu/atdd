"""acc:govern-registry:E004-UNIT-003 — what widening the proof must NOT change.

Only the vocabulary of accepted evidence widened. The two proofs that already
existed keep working, advisory keeps having to carry proof, and documentation-only
cannot acquire enforcement it never claimed.

The documentation-only arm is the sharpest of these. A bound realization is real
evidence, so the tempting inference is that a documentation-only rule with one
"is really enforced after all". It is not: disposition is a declaration about
whether the rule gates, and a provider that happens to emit its id does not
promote it. Reverse coherence must keep judging it on the documentation-only rule
— carries no ``validator:`` — and nothing else.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.rule_id_registry import RuleMetadata
from atdd.coach.validators import test_rule_validator_binding as reverse
from atdd.coach.validators._bound_realization import BoundRealizationResolver
from atdd.coach.validators.tests import _e004_substrate as fx

pytestmark = [pytest.mark.coach]

_CONV = Path("plan/fixture/fixture.convention.yaml")


def _run(monkeypatch, root, registry):
    monkeypatch.setattr(reverse, "build_registry", lambda: registry)
    monkeypatch.setattr(
        reverse,
        "_realization_resolver",
        lambda: None if root is None else BoundRealizationResolver.for_repo(root),
    )
    return reverse._build_violations()


def test_the_live_registry_still_passes_end_to_end():
    """The real corpus, unmocked: widening the proof reds nothing that was green.

    This is the clean baseline #1207's standard requires alongside the faults —
    over every rule the toolkit actually declares, resolved through whichever of
    the three proofs applies.
    """
    assert reverse._build_violations() == []


def test_a_literal_bind_rule_binding_still_proves_a_rule(tmp_path, monkeypatch):
    """Proof 1, over a real validator that really does bind its rule."""
    registry = {
        "coach.rule-id.validator-binding-violation": RuleMetadata(
            rule_id="coach.rule-id.validator-binding-violation",
            convention_path=_CONV,
            disposition="strict",
            validator=(
                "test_rule_validator_binding::test_every_enforced_rule_has_real_validator"
            ),
        )
    }
    # No substrate at all, so ONLY the literal binding can be carrying this.
    bare = tmp_path / "bare"
    bare.mkdir()

    assert _run(monkeypatch, bare, registry) == []


def test_a_convention_variant_still_proves_a_rule(tmp_path, monkeypatch):
    """Proof 2 (#1207): accepted by resolution, with no bind_rule literal.

    Driven from the LIVE registry rather than a synthesised declaration — the
    23 rules that already discharge this way are the thing that must not regress,
    and a fabricated variant reference would prove only that the branch exists.
    """
    from atdd.coach.utils.rule_id_registry import build_registry

    live = build_registry()
    variant_rules = {
        rid: meta
        for rid, meta in live.items()
        if rid == meta.rule_id
        and meta.validator
        and meta.validator.startswith("conventions/")
        and meta.disposition in reverse._ENFORCED_DISPOSITIONS
    }
    assert variant_rules, "the convention-variant discharge is the premise of this arm"

    # No substrate at all, so ONLY `is_convention` can be carrying these.
    bare = tmp_path / "bare"
    bare.mkdir()

    assert _run(monkeypatch, bare, variant_rules) == [], (
        "every rule discharged by an executing convention variant must still "
        "discharge that way after the third proof is added"
    )


def test_advisory_remains_an_enforced_disposition_requiring_proof(
    tmp_path, monkeypatch
):
    """Advisory is not a lighter obligation — it is enforced, so it needs proof."""
    registry = {
        fx.RULE_ID: RuleMetadata(
            rule_id=fx.RULE_ID,
            convention_path=_CONV,
            disposition="advisory",
        )
    }
    bare = tmp_path / "bare"
    bare.mkdir()

    violations = _run(monkeypatch, bare, registry)
    assert len(violations) == 1
    assert "'advisory'" in violations[0].detail

    # …and the third proof discharges advisory exactly as it discharges strict:
    # what changed is the evidence accepted, not which dispositions must supply it.
    root = fx.build_complete(tmp_path / "with_substrate")
    assert _run(monkeypatch, root, registry) == []


def test_documentation_only_cannot_acquire_enforcement_from_a_realization(
    tmp_path, monkeypatch
):
    """A bound realization does not promote an unenforced rule."""
    root = fx.build_complete(tmp_path)

    clean = {
        fx.RULE_ID: RuleMetadata(
            rule_id=fx.RULE_ID, convention_path=_CONV, disposition="documentation-only"
        )
    }
    assert _run(monkeypatch, root, clean) == [], (
        "a documentation-only rule with no validator: is correct, and a bound "
        "realization neither helps nor harms it"
    )

    declaring = {
        fx.RULE_ID: RuleMetadata(
            rule_id=fx.RULE_ID,
            convention_path=_CONV,
            disposition="documentation-only",
            validator="test_rule_validator_binding::test_every_enforced_rule_has_real_validator",
        )
    }
    violations = _run(monkeypatch, root, declaring)
    assert len(violations) == 1, (
        "documentation-only must still refuse a validator: field — a complete "
        "realization must not buy it an exemption from its own rule"
    )
    assert "documentation-only but carries" in violations[0].detail
