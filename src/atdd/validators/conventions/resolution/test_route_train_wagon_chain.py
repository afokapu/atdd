# URN: test:validate-conventions:resolution-variants:route_train_wagon_chain
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `resolution/route_train_wagon_chain` (#1206).

Instantiates the `resolution/reference_chain_resolution` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.resolution.archetype import TEMPLATE_IDS

FAMILY = "resolution"
TEMPLATE = "reference_chain_resolution"
VARIANT = "route_train_wagon_chain"
QUESTION = 'Does a multi-hop reference chain resolve completely?'
SELECTOR = 'nodes that declare chained references or transitive dependencies'
TRAVERSAL = 'start node -> ref A -> target node -> ref B -> final target'
INVARIANT = 'all hops resolve; no missing intermediate target'
AUTO_CAPTURE = 'a new node is included if it declares a chain shape using standard traversal metadata'
FAILURE_EVIDENCE = ['start_node', 'chain_path', 'failed_hop', 'missing_ref']
LEGACY_PARITY_SOURCES = ['src/atdd/coder/validators/test_route_train_wagon_coverage.py']


def test_route_train_wagon_chain_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in resolution archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
