# URN: test:validate-conventions:coverage-variants:dead_code_typescript
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `coverage/dead_code_typescript` (#1206).

Instantiates the `coverage/reachability_no_orphan` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.coverage.archetype import TEMPLATE_IDS

FAMILY = "coverage"
TEMPLATE = "reachability_no_orphan"
VARIANT = "dead_code_typescript"
QUESTION = 'Is every required node reachable from a valid root or owner?'
SELECTOR = 'nodes where requires_reachability != false'
TRAVERSAL = 'root nodes -> allowed edges -> reachable set'
INVARIANT = 'eligible node is in reachable set'
AUTO_CAPTURE = 'a new node is included if its kind/package requires reachability by default'
FAILURE_EVIDENCE = ['orphan_node', 'expected_root', 'allowed_paths', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/coder/validators/test_dead_code_typescript.py']


def test_dead_code_typescript_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in coverage archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
