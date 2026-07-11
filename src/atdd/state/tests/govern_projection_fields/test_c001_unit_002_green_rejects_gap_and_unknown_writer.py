# URN: test:govern-projection-fields:define-field-ownership:C001-UNIT-002-green-rejects-gap-and-unknown-writer
# Acceptance: acc:govern-projection-fields:C001-UNIT-002-green-rejects-gap-and-unknown-writer
# WMBT: wmbt:govern-projection-fields:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the coverage check rejects both an omitted projection field (naming it) and a field whose writer is outside the declared writer set (naming the field `phase` and the unknown writer 'human'), and accepts the policy that covers every field with a declared writer Refs #1400.
"""Both authoring faults are refused, and the good policy is accepted (C001-UNIT-002).

wagon: govern-projection-fields | feature: define-field-ownership | phase: RED
WMBT: wmbt:govern-projection-fields:C001

Two ways to author a policy that cannot be enforced, and they fail in opposite directions:

- an **omitted field** is owned by nobody, so every writer may write it;
- an **unknown writer** owns a field nobody can ever be resolved to, so nobody may write it.

The second is the subtler one, and ``human`` is the example that matters. A human is an
*actor* — the identity that made a commit — and never a *writer*, which is the subsystem
that owns a field. A policy naming ``human`` as the writer of ``phase`` reads perfectly
well in English and is unenforceable in code, so it is refused by name.
"""
from __future__ import annotations

from atdd.state import ownership
from atdd.state.ownership import MERGE_RULES, WRITERS

from ._helpers import policy_document, shipped_policy_document


def test_c001_unit_002_green_rejects_gap_and_unknown_writer() -> None:
    """A gap is rejected, an unknown writer is rejected, and a complete policy is accepted."""
    # 1. The gap: the report names the omitted field.
    gapped = ownership.check_coverage(policy_document(omit="body"))
    assert not gapped.ok
    assert gapped.uncovered == ["body"]
    assert "body" in gapped.render()

    # 2. The unknown writer: the report names the FIELD and the offending writer.
    aliened = ownership.check_coverage(policy_document(writer={"phase": "human"}))
    assert not aliened.ok
    assert aliened.unknown_writers == [("phase", "human")]
    rendered = aliened.render()
    assert "phase" in rendered and "human" in rendered
    assert "not a writer" in rendered, "the report says WHY 'human' cannot own a field"
    assert not aliened.uncovered, "the coverage is complete; only the writer is wrong"

    # An unknown merge rule is refused the same way — a rule the driver cannot dispatch on
    # owns the field just as uselessly.
    ruleless = ownership.check_coverage(policy_document(rule={"slug": "last-writer-wins"}))
    assert not ruleless.ok
    assert ruleless.unknown_rules == [("slug", "last-writer-wins")]

    # 3. The policy this repository actually commits covers every field with a declared
    #    writer and a declared rule — and is accepted.
    shipped = ownership.check_coverage(shipped_policy_document())
    assert shipped.ok, shipped.render()
    assert shipped.checked == len(ownership.schema_fields())

    policy = ownership.FieldOwnershipPolicy.from_document(shipped_policy_document())
    for field in ownership.schema_fields():
        assert policy.writer_of(field) in WRITERS
        assert policy.rule_of(field) in MERGE_RULES
