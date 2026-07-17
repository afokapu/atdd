# URN: test:state-store:projection:schema-matches-authored-contract
# Issue: #1433 (#1400)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""The projection module's schema constants ARE the authored contract (#1400).

``contracts/commons/projection-object.schema.json`` is the authored source of truth
for the projection document's shape. It is deliberately NOT vendored under
``src/atdd/state/`` — that layer holds operational data and storage APIs, never
authored definitions (``coder.state-store.operational-vs-definition-sot``) — so
:mod:`atdd.state.projection` carries the shape as executable Python constants.

Two copies of one truth drift. This test is the tie: change the contract without
changing the constants (or the reverse) and it fails, naming the field.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.state.identity import UID_RE
from atdd.state.projection import FIELD_TYPES, PHASES, REQUIRED_FIELDS, STATES

_CONTRACT = (
    Path(__file__).resolve().parents[4] / "contracts" / "commons" / "projection-object.schema.json"
)


@pytest.fixture(scope="module")
def schema() -> dict:
    if not _CONTRACT.is_file():
        pytest.fail(f"authored contract missing: {_CONTRACT}")
    return json.loads(_CONTRACT.read_text(encoding="utf-8"))


def test_every_contract_field_is_known_to_the_projector(schema) -> None:
    """The admitted field set matches the contract's properties, exactly."""
    assert set(FIELD_TYPES) == set(schema["properties"]), (
        "projection.FIELD_TYPES has drifted from commons:projection-object"
    )
    # The contract forbids extra properties, which is what makes FIELD_TYPES total.
    assert schema["additionalProperties"] is False


def test_required_fields_match_the_contract(schema) -> None:
    assert sorted(REQUIRED_FIELDS) == sorted(schema["required"])


def test_vocabularies_match_the_contract(schema) -> None:
    """The phase enum, the state enum, and the uid pattern are the contract's."""
    assert list(PHASES) == schema["properties"]["phase"]["enum"]
    assert list(STATES) == schema["properties"]["state"]["enum"]
    assert UID_RE.pattern == schema["properties"]["uid"]["pattern"]

    # COMPLETE is derived from merge-to-main, never committed (spec §18 decision 1).
    assert "COMPLETE" not in PHASES
