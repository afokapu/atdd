# URN: test:govern-lifecycle:define-transition-autonomy:D020-UNIT-003-node-is-schema-valid-and-paired-with-its-sibling
# Acceptance: acc:govern-lifecycle:D020-UNIT-003-node-is-schema-valid-and-paired-with-its-sibling
# WMBT: wmbt:govern-lifecycle:D020
# Phase: GREEN
# Layer: unit
# Assertion: structural
"""D020-UNIT-003 — the node is well-formed and reads as a pair with its sibling.

The sibling is ``coach.execution.freedom-with-a-leash``: same shape, one axis
over. That node governs which TOOLS run unattended (its terms are
``freedom_set`` and ``leash``); this one governs which TRANSITIONS may be
submitted unattended. The pairing is the point — two nodes describing one model
on two axes, not a second vocabulary for the same idea.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.coach, pytest.mark.platform]

_NODE_REL = Path(
    "src/atdd/coach/conventions/nodes/coach.lifecycle.transition-autonomy.convention.yaml"
)
_SIBLING_REL = Path(
    "src/atdd/coach/conventions/nodes/coach.execution.freedom-with-a-leash.convention.yaml"
)
_SCHEMA_REL = Path("src/atdd/planner/schemas/author/convention-node.schema.json")

_RULE_ID = "coach.lifecycle.transition-autonomy"
_SIBLING_RULE_ID = "coach.execution.freedom-with-a-leash"


def _node() -> dict:
    path = find_repo_root() / _NODE_REL
    assert path.is_file(), (
        f"REGRESSION: {_NODE_REL} does not exist yet. GREEN authors it under "
        "the existing convention-node pattern."
    )
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@pytest.mark.platform
def test_node_validates_against_the_convention_node_schema() -> None:
    """It is authored from the same draft-07 schema every node under nodes/ is."""
    import json

    import jsonschema

    schema = json.loads((find_repo_root() / _SCHEMA_REL).read_text(encoding="utf-8"))
    jsonschema.validate(instance=_node(), schema=schema)


@pytest.mark.platform
def test_rule_id_matches_the_grammar_and_the_lifecycle_family() -> None:
    """<archetype>.<convention_short_name>.<rule_name>, in the coach.lifecycle family."""
    node = _node()
    assert node.get("rule_id") == _RULE_ID, (
        f"rule_id must be {_RULE_ID!r}; got {node.get('rule_id')!r}"
    )
    archetype, family, _name = _RULE_ID.split(".", 2)
    assert (archetype, family) == ("coach", "lifecycle"), (
        "the node belongs beside coach.lifecycle.phase-machine, so its rule_id "
        "must sit in the coach.lifecycle family"
    )


@pytest.mark.platform
def test_node_carries_the_declarative_first_posture() -> None:
    """Declared, not yet mechanically enforced — the same posture as the sibling."""
    node = _node()
    assert node.get("kind") == "principle", (
        f"kind must be 'principle'; got {node.get('kind')!r}"
    )
    metadata = node.get("metadata") or {}
    assert metadata.get("severity") == 3, (
        f"severity must be 3, matching the sibling; got {metadata.get('severity')!r}"
    )
    assert metadata.get("disposition") == "documentation-only", (
        "disposition must be 'documentation-only' — the declarative-first "
        f"decision on #1626; got {metadata.get('disposition')!r}"
    )


@pytest.mark.platform
def test_node_names_its_sibling_explicitly() -> None:
    """The two must read as one model on two axes, not as unrelated nodes."""
    node = _node()
    prose = " ".join(
        [str(node.get("statement", "")), str(node.get("rationale", "")), str(node.get("notes", ""))]
        + [str(t.get("text", "")) for t in (node.get("terms") or [])]
    )
    assert _SIBLING_RULE_ID in prose, (
        f"the node never names {_SIBLING_RULE_ID}, so a reader has no way to find "
        "the sibling that governs the same question on the tool axis"
    )


@pytest.mark.platform
def test_terms_reuse_the_siblings_vocabulary_on_the_transition_axis() -> None:
    """freedom_set / leash carried onto transitions, not a parallel coinage."""
    sibling = yaml.safe_load((find_repo_root() / _SIBLING_REL).read_text(encoding="utf-8")) or {}
    sibling_terms = {t["term_id"] for t in (sibling.get("terms") or [])}
    assert {"freedom_set", "leash"} <= sibling_terms, (
        "precondition failed: the sibling no longer defines freedom_set/leash, "
        f"so this pairing check is stale; sibling terms are {sorted(sibling_terms)}"
    )

    terms = {t["term_id"]: str(t.get("text", "")) for t in (_node().get("terms") or [])}
    assert terms, "the node declares no terms"
    echoed = [tid for tid in terms if "freedom" in tid or "leash" in tid]
    assert echoed, (
        "no term_id echoes the sibling's freedom_set/leash pairing; the node "
        f"coins a parallel vocabulary instead. Terms are: {sorted(terms)}"
    )


@pytest.mark.platform
def test_source_block_records_provenance_in_the_established_shape() -> None:
    """Promotion of prose into a node carries the same provenance the sibling used."""
    source = _node().get("source") or {}
    missing = [
        key
        for key in ("legacy_path", "legacy_section", "extraction_mode")
        if not source.get(key)
    ]
    assert not missing, (
        f"the source block is missing {missing}; the established promotion "
        "pattern records legacy_path/legacy_section/extraction_mode (see the "
        "sibling's promotion from session.convention.yaml)"
    )
    assert "phase_machine.convention.yaml" in str(source.get("legacy_path")), (
        "legacy_path must point at phase_machine.convention.yaml, the prose this "
        f"axis is promoted from; got {source.get('legacy_path')!r}"
    )
