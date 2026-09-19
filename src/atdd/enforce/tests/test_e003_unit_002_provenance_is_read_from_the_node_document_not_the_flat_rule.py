# URN: test:govern-registry:E003-UNIT-002-provenance-is-read-from-the-node-document-not-the-flat-rule
# Acceptance: acc:govern-registry:E003-UNIT-002-provenance-is-read-from-the-node-document-not-the-flat-rule
# WMBT: wmbt:govern-registry:E003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:E003-UNIT-002-provenance-is-read-from-the-node-document-not-the-flat-rule.

Twin detection reads ``source.legacy_rule_id`` off the extension node DOCUMENT.
The flat single-node projection that monolith ``rules:[]`` consumers expect
(:func:`single_node_rule_dict`) keeps ten keys and ``source`` is not among them, so
provenance keyed off that projection is not merely lossy — it is absent, and a
coverage measure built on it reports every mirrored core rule as uncovered.

This is pinned as an acceptance rather than left as a comment because the projection
lives in the module a provenance-aware registry filter is slated to land in
(``atdd.coach.utils.rule_binding``, #1973 GREEN). A filter reading ``rule["source"]``
there finds no mirrors at all.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.coach.utils.rule_binding import single_node_rule_dict
from atdd.enforce.twin_coverage import (
    measure_twin_coverage,
    twins_by_core_rule,
    why_not_verdicts,
)

from .conftest import write_mirror_node

_MIRRORED = "coder.dead-code.reachability"


def test_provenance_is_read_from_the_node_document_not_the_flat_rule(tmp_path: Path) -> None:
    core_ids = [_MIRRORED]
    node = write_mirror_node(tmp_path, rule_id=_MIRRORED, legacy_rule_id=_MIRRORED)
    no_record = why_not_verdicts(tmp_path / "absent.md")

    # Read as a node document: the legacy_rule_id is present, so the core rule it
    # names is covered by its twin.
    twins = twins_by_core_rule(tmp_path)
    assert twins[_MIRRORED] == (_MIRRORED,)
    from_document = measure_twin_coverage(core_ids, twins=twins, why_not=no_record)
    assert from_document.uncovered == ()
    assert from_document.move_ready is True

    # Read through the flat projection: the rule survives, the provenance does not.
    flat = single_node_rule_dict(yaml.safe_load(node.read_text(encoding="utf-8")))
    assert flat is not None, "the node is a single-node convention document"
    assert flat["id"] == _MIRRORED, "the rule_id survives the projection"
    assert "source" not in flat, (
        "single_node_rule_dict must be shown to drop source — if it ever carries it, "
        "this acceptance is obsolete and the warning it encodes can be retired"
    )

    # So a twin map derived from the projection is empty: no provenance is recoverable.
    projected_source = flat.get("source") or {}
    flat_twins: dict[str, tuple[str, ...]] = {}
    if projected_source.get("legacy_rule_id"):
        flat_twins[projected_source["legacy_rule_id"]] = (flat["id"],)
    assert flat_twins == {}

    # And coverage measured from it reports the mirrored rule as uncovered — the
    # same 1-of-1 shortfall that, over the real substrate, reads as 128 instead of 96.
    from_projection = measure_twin_coverage(core_ids, twins=flat_twins, why_not=no_record)
    assert from_projection.uncovered == (_MIRRORED,)
    assert from_projection.move_ready is False
