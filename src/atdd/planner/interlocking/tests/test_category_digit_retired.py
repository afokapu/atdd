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
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from atdd.planner.interlocking import (
    load_interlocking,
    load_schema,
    validate_interlocking,
)
from atdd.planner.interlocking.models import Route
from atdd.planner.interlocking.tests._fixtures import interlocking_doc

# Typed identities (#1421 grammar) — no digit anywhere to parse.
_NOMINAL_ID = "train:match-resolution:standard"
_NOMINAL_PATH = "plan/_trains/match-resolution/standard.yaml"
_ALTERNATE_ID = "train:match-resolution:timeout"
_ALTERNATE_PATH = "plan/_trains/match-resolution/timeout.yaml"


def _typed_train(train_id: str, category: str, intent: str) -> Dict[str, Any]:
    """A target train in the post-#1421 shape: typed id + ``category`` FIELD."""
    return {
        "train_id": train_id,
        "title": f"Train {train_id}",
        "description": f"Linear train {train_id} for interlocking category tests.",
        "category": category,
        "themes": ["match"],
        "participants": ["wagon:blitz", "wagon:player"],
        "sequence": [
            {
                "step": 1,
                "intent": intent,
                "from": "wagon:blitz",
                "to": "wagon:player",
                "artifact": "match:result",
            }
        ],
    }


def typed_interlocking_doc() -> Dict[str, Any]:
    """The shared interlocking, retyped: typed ``train_id``s, no ``category_digit``."""
    doc = copy.deepcopy(interlocking_doc())
    for route, train_id, train_path in (
        (doc["routes"][0], _NOMINAL_ID, _NOMINAL_PATH),
        (doc["routes"][1], _ALTERNATE_ID, _ALTERNATE_PATH),
    ):
        route.pop("category_digit", None)
        route["train_id"] = train_id
        route["train_path"] = train_path
    return doc


def write_typed_tree(root: Path, doc: Dict[str, Any] | None = None) -> Path:
    """Materialize the typed trains + interlocking under ``root``; return its path."""
    doc = doc if doc is not None else typed_interlocking_doc()
    trains_dir = root / "plan" / "_trains"
    il_dir = trains_dir / "_interlockings"
    il_dir.mkdir(parents=True, exist_ok=True)

    for train_path, train in (
        (_NOMINAL_PATH, _typed_train(_NOMINAL_ID, "nominal", "Close match on quorum")),
        (_ALTERNATE_PATH, _typed_train(_ALTERNATE_ID, "alternate", "Close match on timeout")),
    ):
        target = root / train_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(train, sort_keys=False), encoding="utf-8")

    (trains_dir / "_interlockings.yaml").write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "interlockings": [
                    {
                        "interlocking_id": doc["interlocking_id"],
                        "path": doc["source"]["path"],
                        "theme": doc["theme"],
                        "status": doc["status"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    il_path = il_dir / "match-resolution.yaml"
    il_path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return il_path


# --------------------------------------------------------------------------- #
# the defect: a typed interlocking must load and validate clean
# --------------------------------------------------------------------------- #
def test_typed_digit_free_interlocking_is_sound(tmp_path):
    """A digit-free interlocking whose routes agree with their trains has NO violations.

    This is the test #1421 never wrote. Under the digit path it fails twice over:
    the loader demands a ``category_digit`` key that no migrated route carries, and
    the category check reads ``"r"`` out of ``train:match-resolution:standard``.
    """
    il = load_interlocking(write_typed_tree(tmp_path))
    assert validate_interlocking(il, tmp_path) == []


def test_route_category_must_agree_with_target_train_category_field(tmp_path):
    """Disagreement is judged against the train's ``category`` FIELD, not an identity."""
    doc = typed_interlocking_doc()
    doc["routes"][0]["category"] = "exception"  # target train declares `nominal`
    il = load_interlocking(write_typed_tree(tmp_path, doc))

    violations = validate_interlocking(il, tmp_path)

    assert violations, "a route disagreeing with its train's category must be flagged"
    assert any("category" in v.detail.lower() for v in violations)


def test_category_agreement_never_parses_the_train_id(tmp_path):
    """No violation may be justified by a digit — the grammar #1421 retired."""
    doc = typed_interlocking_doc()
    doc["routes"][0]["category"] = "exception"
    il = load_interlocking(write_typed_tree(tmp_path, doc))

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
        "train_id": _NOMINAL_ID,
        "train_path": _NOMINAL_PATH,
        "projection": {"expected_sequence_digest": "deadbeef"},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(route, route_schema)
