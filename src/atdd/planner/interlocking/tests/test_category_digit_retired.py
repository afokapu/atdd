# URN: test:plan:train-interlocking:category-digit-retired
# Issue: #1440 (follows #1421)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1440 — the interlocking layer carries NO category digit (finishes #1421).

#1421 moved a train's variant classification OUT of its identity and into a
``category`` FIELD, precisely so a reclassification changes metadata instead of
identity. ``sanity.route_category_violations`` was flipped to the field compare,
but a PARALLEL path in :mod:`validate` was missed: it still derived the category
from character 2 of the ``train_id`` and compared ``route.category_digit``.

A typed ``train:<subject>:<slug>`` identity has no digit at index 1 — so that
check reads ``"r"`` out of ``"train:..."`` and flags every sound route. It stayed
green only because no interlocking artifact exists on disk, leaving the path
dormant. These tests exercise it against a typed, digit-free interlocking, which
is what CI never did.

The contract pinned here: route category is judged by comparing the route's
``category`` against the ``category`` FIELD of the target train — never by
parsing an identity, and never via a retired ``category_digit``.
"""
from __future__ import annotations

import copy
from dataclasses import fields

import pytest

from atdd.planner.interlocking import (
    load_interlocking,
    load_schema,
    validate_interlocking,
)
from atdd.planner.interlocking.models import Route
from atdd.planner.interlocking.tests._fixtures import (
    NOMINAL_TRAIN_ID,
    NOMINAL_TRAIN_PATH,
    interlocking_doc,
    write_tree,
)


# --------------------------------------------------------------------------- #
# the defect: a typed interlocking must load and validate clean
# --------------------------------------------------------------------------- #
def test_typed_digit_free_interlocking_is_sound(tmp_path):
    """A digit-free interlocking whose routes agree with their trains has NO violations.

    This is the test #1421 never wrote. Under the digit path it fails twice over:
    the loader demands a ``category_digit`` key that no migrated route carries, and
    the category check reads ``"r"`` out of ``train:match-resolution:standard``.
    """
    il = load_interlocking(write_tree(tmp_path))
    assert validate_interlocking(il, tmp_path) == []


def test_route_category_must_agree_with_target_train_category_field(tmp_path):
    """Disagreement is judged against the train's ``category`` FIELD, not an identity."""
    doc = copy.deepcopy(interlocking_doc())
    doc["routes"][0]["category"] = "exception"  # target train declares `nominal`
    il = load_interlocking(write_tree(tmp_path, doc))

    violations = validate_interlocking(il, tmp_path)

    assert violations, "a route disagreeing with its train's category must be flagged"
    assert any("category" in v.detail.lower() for v in violations)


def test_category_agreement_never_parses_the_train_id(tmp_path):
    """No violation may be justified by a digit — the grammar #1421 retired."""
    doc = copy.deepcopy(interlocking_doc())
    doc["routes"][0]["category"] = "exception"
    il = load_interlocking(write_tree(tmp_path, doc))

    for violation in validate_interlocking(il, tmp_path):
        assert "digit" not in violation.detail.lower(), (
            f"category is a FIELD (#1421); a digit-derived violation means the "
            f"interlocking still parses the identity: {violation.detail!r}"
        )


# --------------------------------------------------------------------------- #
# the residue: model + schema must not carry the digit at all
# --------------------------------------------------------------------------- #
def test_route_model_carries_no_category_digit():
    assert "category_digit" not in {f.name for f in fields(Route)}


def test_models_expose_no_category_by_digit_map():
    import atdd.planner.interlocking.models as models

    assert not hasattr(models, "CATEGORY_BY_DIGIT"), (
        "the digit->category map is the retired grammar; category is a train FIELD"
    )


def test_schema_rejects_a_route_carrying_category_digit():
    import jsonschema

    route_schema = load_schema()["definitions"]["route"]
    route = {
        "route_id": "nominal",
        "category": "nominal",
        "category_digit": "0",
        "priority": 0,
        "guard_ref": "guard:always",
        "train_id": NOMINAL_TRAIN_ID,
        "train_path": NOMINAL_TRAIN_PATH,
        "projection": {"expected_sequence_digest": "deadbeef"},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(route, route_schema)
