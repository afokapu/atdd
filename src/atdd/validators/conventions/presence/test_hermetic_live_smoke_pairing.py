# URN: test:validate-conventions:presence-variants:hermetic_live_smoke_pairing
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `presence/hermetic_live_smoke_pairing` (#1206).

Instantiates the `presence/required_relationship_presence` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.presence.archetype import TEMPLATE_IDS

FAMILY = "presence"
TEMPLATE = "required_relationship_presence"
VARIANT = "hermetic_live_smoke_pairing"
QUESTION = 'Does every eligible node have a required outgoing relationship or child edge?'
SELECTOR = 'nodes whose schema/kind declares required relationships'
TRAVERSAL = 'node -> required_relationship_type -> target nodes'
INVARIANT = 'required relationship target set is non-empty'
AUTO_CAPTURE = 'a new node is included if its schema declares required relationships'
FAILURE_EVIDENCE = ['node_id', 'missing_relationship', 'expected_target_kind', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/tester/validators/test_hermetic_live_smoke_pairing.py']


def test_hermetic_live_smoke_pairing_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in presence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
