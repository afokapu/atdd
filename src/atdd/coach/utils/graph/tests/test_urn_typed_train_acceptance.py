# URN: test:coach:urn:typed_train_acceptance
"""
Issue #1548 — a typed train acceptance was UNAUTHORABLE.

``acc`` was declared ``segment_count: 2, parent: wagon`` and its second segment
forbade colons, so the train-acceptance shape the substrate spec documents
(``acc:<train-id>:<acceptance-slug>``) could not be spelled once ``#1421`` made
the train identity typed (``train:<subject>:<slug>``). The example in
``train.convention.yaml`` still used the retired ``NNNN-slug`` form, so anyone
following the documentation produced an artifact that could not validate.

These tests pin BOTH acceptance shapes — the wagon-parented one (unchanged) and
the train-parented one (newly admitted) — through the two public entry points
that police URNs: ``validate_urn`` (regex) and ``validate_grammar`` (regex +
parent-it-belongs-to segment count). They also pin that the polymorphism is
*bounded*: malformed near-misses must still be rejected.
"""

from __future__ import annotations

import pytest

from atdd.coach.utils.graph.urn import URNGrammar


TYPED_TRAIN_ACC = "acc:train:self-compliance:validate-lifecycle:idempotent-on-retry"
WAGON_ACC = "acc:author-plan-substrate:E004-UNIT-002-carries-schema-required-keys"


# ---------------------------------------------------------------------------
# The shape that #1548 unblocks
# ---------------------------------------------------------------------------


def test_typed_train_acceptance_is_regex_valid():
    assert URNGrammar.validate_urn(TYPED_TRAIN_ACC, "acc") is True


def test_typed_train_acceptance_passes_grammar_segment_count():
    """4 tokens: the train parent contributes 3 (train, subject, slug), +1 leaf."""
    assert URNGrammar.validate_grammar(TYPED_TRAIN_ACC) is True


def test_typed_train_acceptance_parses_to_a_whole_train_id():
    """The parent is reassembled, not split across positional fields."""
    parsed = URNGrammar.parse_urn(TYPED_TRAIN_ACC)
    assert parsed["type"] == "acceptance"
    assert parsed["parent_kind"] == "train"
    assert parsed["train_id"] == "train:self-compliance:validate-lifecycle"
    assert parsed["slug"] == "idempotent-on-retry"


def test_parsed_train_id_is_itself_a_valid_train_urn():
    """Round-trip: the parent extracted from the acceptance must resolve as a train."""
    parsed = URNGrammar.parse_urn(TYPED_TRAIN_ACC)
    assert URNGrammar.validate_grammar(parsed["train_id"]) is True


# ---------------------------------------------------------------------------
# The pre-existing shape must be untouched
# ---------------------------------------------------------------------------


def test_wagon_parented_acceptance_still_validates():
    assert URNGrammar.validate_urn(WAGON_ACC, "acc") is True
    assert URNGrammar.validate_grammar(WAGON_ACC) is True


def test_wagon_parented_acceptance_still_parses_to_facets():
    parsed = URNGrammar.parse_urn(WAGON_ACC)
    assert parsed["parent_kind"] == "wagon"
    assert parsed["wagon_id"] == "author-plan-substrate"
    assert parsed["wmbt_id"] == "E004"
    assert parsed["harness"] == "UNIT"
    assert parsed["sequence"] == "002"


def test_legacy_train_acceptance_slug_shape_still_validates():
    """``acc:<wagon-or-legacy-train>:<slug>`` — the 2-token slug form."""
    assert URNGrammar.validate_grammar("acc:self-compliance:idempotent-on-retry") is True


# ---------------------------------------------------------------------------
# The polymorphism is BOUNDED — near-misses stay rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "urn,why",
    [
        ("acc:train:self-compliance:validate-lifecycle", "train parent with no leaf slug"),
        (
            "acc:train:self-compliance:validate-lifecycle:a:b",
            "one token too many after the train parent",
        ),
        ("acc:train:Self-Compliance:validate-lifecycle:x", "uppercase in the subject"),
        ("acc:train:self-compliance:validate-lifecycle:X-Y", "uppercase in the leaf slug"),
        ("acc:train:-leading-dash:validate-lifecycle:x", "subject may not start with a dash"),
    ],
)
def test_malformed_typed_train_acceptance_is_rejected(urn, why):
    assert URNGrammar.validate_urn(urn, "acc") is False, why


def test_three_token_acceptance_is_still_a_segment_count_error():
    """3 tokens is neither the wagon shape (2) nor the train shape (4)."""
    with pytest.raises(ValueError, match="wrong segment count"):
        URNGrammar.validate_grammar("acc:some-wagon:some-feature:some-slug")


def test_segment_count_error_names_both_admissible_counts():
    """The operator must be told BOTH shapes exist, not just the canonical one."""
    with pytest.raises(ValueError) as exc:
        URNGrammar.validate_grammar("acc:some-wagon:some-feature:some-slug")
    assert "2 or 4" in str(exc.value)


# ---------------------------------------------------------------------------
# The canonical projections keep their existing contract
# ---------------------------------------------------------------------------


def test_segment_counts_projection_stays_an_int():
    """`alternate_segment_counts` must not leak into SEGMENT_COUNTS — the
    root-family derivation in edge_validator compares it to the int 1."""
    assert URNGrammar.SEGMENT_COUNTS["acc"] == 2


def test_no_other_family_declares_alternate_segment_counts():
    """`acc` is the sole family with a polymorphic parent; keep it that way
    deliberately rather than by accident."""
    with_alternates = {
        family
        for family, spec in URNGrammar._FAMILY_SPECS.items()
        if (spec or {}).get("alternate_segment_counts")
    }
    assert with_alternates == {"acc"}
