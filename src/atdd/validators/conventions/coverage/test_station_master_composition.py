# URN: test:validate-conventions:coverage-variants:station_master_composition
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `coverage/station_master_composition` (#1206).

Instantiates the `coverage/source_has_required_target` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.coverage.archetype import TEMPLATE_IDS

FAMILY = "coverage"
TEMPLATE = "source_has_required_target"
VARIANT = "station_master_composition"
QUESTION = 'For every source node of type X, does required downstream target Y exist?'
SELECTOR = 'nodes where node.coverage.requires exists'
TRAVERSAL = 'source node -> required relationship/path -> target node set'
INVARIANT = 'target set is non-empty and satisfies required target kind/filter'
AUTO_CAPTURE = 'a new node is included if it declares coverage requirements'
FAILURE_EVIDENCE = ['source_node', 'required_target_kind', 'required_path', 'actual_targets']
LEGACY_PARITY_SOURCES = ['src/atdd/coder/validators/test_station_master_pattern.py']


def test_station_master_composition_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in coverage archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
