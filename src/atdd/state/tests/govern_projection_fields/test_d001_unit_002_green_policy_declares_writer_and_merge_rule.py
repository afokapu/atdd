# URN: test:govern-projection-fields:define-field-ownership:D001-UNIT-002-green-policy-declares-writer-and-merge-rule
# Acceptance: acc:govern-projection-fields:D001-UNIT-002-green-policy-declares-writer-and-merge-rule
# WMBT: wmbt:govern-projection-fields:D001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the committed field-ownership policy resolves every projection schema field to exactly one writer among the six and exactly one merge rule among the eight — uid to core-create/immutable and external_refs to extension-bot/bot-only — loadable as data, conforming to the authored contract, and byte-identical to the table core ships Refs #1400.
"""The policy is machine-readable data, and it is complete (D001-UNIT-002).

wagon: govern-projection-fields | feature: define-field-ownership | phase: RED
WMBT: wmbt:govern-projection-fields:D001

Ownership stated in a plan document is ownership nothing enforces. This is the same table as
declared **data**: one entry per projection field, naming its single legal writer and its
merge rule, read by the field-writer validator and by the merge driver — one declaration, two
consumers, no chance of them drifting apart into two different ideas of who owns ``body``.

The two anchors the acceptance names are the two ends of the boundary: ``uid`` is core's to
mint and nobody's to rewrite, and ``external_refs`` is the extension bot's alone.
"""
from __future__ import annotations

from atdd.state import ownership
from atdd.state.ownership import (
    DEFAULT_POLICY,
    MERGE_RULES,
    RULE_BOT_ONLY,
    RULE_IMMUTABLE,
    WRITER_CORE_CREATE,
    WRITER_EXTENSION_BOT,
    WRITERS,
)

from ._helpers import contract, repo_root, shipped_policy_document


def test_d001_unit_002_green_policy_declares_writer_and_merge_rule() -> None:
    """Every schema field resolves to one writer and one rule; uid and external_refs anchor it."""
    policy = ownership.load_policy(repo_root())

    # Every projection schema field — the projector's own field list, so a new field in the
    # schema makes the policy incomplete rather than leaving that field quietly unowned.
    fields = ownership.schema_fields()
    for name in ("uid", "slug", "phase", "body", "train", "wmbts", "extension_digests",
                 "external_refs", "state"):
        assert name in fields
    for name in fields:
        assert policy.writer_of(name) in WRITERS, name
        assert policy.rule_of(name) in MERGE_RULES, name

    # Exactly one writer and one rule per field: a field declared twice is refused outright.
    assert len(policy.fields) == len(fields)

    # The two anchors.
    assert policy.writer_of("uid") == WRITER_CORE_CREATE
    assert policy.rule_of("uid") == RULE_IMMUTABLE
    assert policy.writer_of("external_refs") == WRITER_EXTENSION_BOT
    assert policy.rule_of("external_refs") == RULE_BOT_ONLY
    # ...and lifecycle code may not even READ the provider's subtree (spec §8.2 rule 5).
    assert policy.owner("external_refs").lifecycle_readable is False

    # It is data, and it conforms to the authored contract: writer is drawn from the
    # contract's enum, and no entry carries a property the contract forbids.
    schema = contract("projection-field-ownership")
    entry_schema = schema["properties"]["fields"]["items"]
    allowed_writers = set(entry_schema["properties"]["writer"]["enum"])
    for entry in shipped_policy_document()["fields"]:
        assert set(entry) <= set(entry_schema["properties"]), entry
        assert set(entry_schema["required"]) <= set(entry), entry
        assert entry["writer"] in allowed_writers, entry

    # The committed file and the table core ships are the same table — so a checkout that has
    # not declared a policy is governed by the same rules as one that has, not by weaker ones.
    assert shipped_policy_document() == ownership.FieldOwnershipPolicy.from_document(
        DEFAULT_POLICY
    ).as_document()
