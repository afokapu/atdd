# URN: test:validate-conventions:acyclicity-variants:no_cross_wagon_consume_cycle
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `acyclicity/no_cross_wagon_consume_cycle` (#1206).

Instantiates the `acyclicity/forbidden_cycle_absence` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.acyclicity.archetype import TEMPLATE_IDS

FAMILY = "acyclicity"
TEMPLATE = "forbidden_cycle_absence"
VARIANT = "no_cross_wagon_consume_cycle"
QUESTION = 'Does a traversal avoid cycles where cycles are forbidden?'
SELECTOR = 'edge types or relationship subgraphs marked acyclic'
TRAVERSAL = 'nodes -> selected edge type/path -> depth-first traversal'
INVARIANT = 'no node appears twice in the same traversal path'
AUTO_CAPTURE = 'a new node is included if it participates in an edge type declared acyclic'
FAILURE_EVIDENCE = ['cycle_path', 'edge_type', 'start_node', 'repeated_node']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_no_cross_wagon_consume_cycle.py']


def test_no_cross_wagon_consume_cycle_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in acyclicity archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
