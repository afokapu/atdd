# URN: test:validate-conventions:composition-variants:package_data_ships_convention_nodes
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `composition/package_data_ships_convention_nodes` (#1206).

Instantiates the `composition/composed_graph_loads` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.composition.archetype import TEMPLATE_IDS

FAMILY = "composition"
TEMPLATE = "composed_graph_loads"
VARIANT = "package_data_ships_convention_nodes"
QUESTION = 'Can all convention sources be loaded into one composed graph?'
SELECTOR = 'all convention source files/packages'
TRAVERSAL = 'source files -> parse -> local graph fragments -> composed graph'
INVARIANT = 'graph construction succeeds with no parse/load errors'
AUTO_CAPTURE = 'a new node is included if it lives in a convention source path included by the graph loader'
FAILURE_EVIDENCE = ['source_file', 'parse_error', 'node_id_if_available', 'package_id']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_composition_data_shipped.py']


def test_package_data_ships_convention_nodes_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in composition archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
