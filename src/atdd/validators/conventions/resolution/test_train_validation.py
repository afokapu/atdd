# URN: test:validate-conventions:resolution-variants:train_validation
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `resolution/train_validation` (#1206).

Instantiates the `resolution/direct_reference_resolution` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.resolution.archetype import TEMPLATE_IDS

FAMILY = "resolution"
TEMPLATE = "direct_reference_resolution"
VARIANT = "train_validation"
QUESTION = 'Does every declared reference resolve to an existing graph target?'
SELECTOR = 'nodes with refs/node_refs/rule_refs/relationship_targets'
TRAVERSAL = 'source node -> reference value -> target index'
INVARIANT = 'target_index.contains(reference)'
AUTO_CAPTURE = 'a new node is included if it declares references using standard ref fields'
FAILURE_EVIDENCE = ['source_node', 'ref_field', 'missing_ref', 'expected_target_kind', 'source_location']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_train_validation.py']


def test_train_validation_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in resolution archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
