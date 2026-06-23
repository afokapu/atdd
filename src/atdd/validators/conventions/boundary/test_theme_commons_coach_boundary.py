# URN: test:validate-conventions:boundary-variants:theme_commons_coach_boundary
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `boundary/theme_commons_coach_boundary` (#1206).

Instantiates the `boundary/allowed_boundary_crossing` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.boundary.archetype import TEMPLATE_IDS

FAMILY = "boundary"
TEMPLATE = "allowed_boundary_crossing"
VARIANT = "theme_commons_coach_boundary"
QUESTION = 'Does this edge, import, or reference cross only allowed package/layer boundaries?'
SELECTOR = 'edges/imports/references with source and target ownership metadata'
TRAVERSAL = 'source node/package -> edge/import/ref -> target node/package -> boundary policy'
INVARIANT = 'boundary_policy.allows(source, target, edge_type)'
AUTO_CAPTURE = 'a new node is included if it declares ownership/package/layer metadata and participates in edges'
FAILURE_EVIDENCE = ['source', 'target', 'edge_type', 'source_boundary', 'target_boundary', 'violated_policy']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_theme_commons_coach_boundary.py']


def test_theme_commons_coach_boundary_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in boundary archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
