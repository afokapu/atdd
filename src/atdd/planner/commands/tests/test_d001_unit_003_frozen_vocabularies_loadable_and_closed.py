# URN: test:author-atdd-substrate:substrate-spine:D001-UNIT-003-frozen-vocabularies-loadable-and-closed
# Acceptance: acc:author-atdd-substrate:D001-UNIT-003-frozen-vocabularies-loadable-and-closed
# WMBT: wmbt:author-atdd-substrate:D001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""D001-UNIT-003 — every frozen vocabulary is loadable and closed (synced to schema)."""
from __future__ import annotations

from atdd.planner.commands.author_schemas import frozen_vocabularies, load_schema


def test_all_vocabularies_loadable():
    vocab = frozen_vocabularies()
    # the full spec §5-§8 enum set
    assert len(vocab) == 15
    for name, members in vocab.items():
        assert isinstance(members, tuple) and len(members) >= 1, name


def test_vocabularies_are_closed_synced_to_schema():
    """The schema enums equal the Python constants — adding a member needs a
    schema change, i.e. the vocabularies are closed, not open-ended."""
    vocab = frozen_vocabularies()
    cn = load_schema("convention-node")["properties"]
    assert set(cn["kind"]["enum"]) == set(vocab["convention_node.kind"])
    assert set(cn["status"]["enum"]) == set(vocab["convention_node.status"])

    rel = load_schema("relationship")["properties"]
    assert set(rel["type"]["enum"]) == set(vocab["relationship.type"])
    assert set(rel["foundation"]["enum"]) == set(vocab["relationship.foundation"])

    sc = load_schema("scope")["properties"]
    assert set(sc["selectors"]["items"]["properties"]["type"]["enum"]) == set(vocab["scope.selector_type"])

    gt = load_schema("gate")["properties"]
    assert set(gt["trigger"]["properties"]["type"]["enum"]) == set(vocab["gate.trigger_type"])
    assert set(gt["on_violation"]["properties"]["action"]["enum"]) == set(vocab["gate.violation_action"])
