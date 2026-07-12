# URN: test:validate-conventions:schema-variants:contract_schema_conformance
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `schema/contract_schema_conformance` (#1206).

Instantiates the `schema/node_schema_conformance` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.schema.archetype import TEMPLATE_IDS

FAMILY = "schema"
TEMPLATE = "node_schema_conformance"
VARIANT = "contract_schema_conformance"
QUESTION = 'Does each node conform to its declared schema?'
SELECTOR = 'nodes where node.schema exists'
TRAVERSAL = 'node -> schema_id -> schema document -> validate node payload'
INVARIANT = 'jsonschema validation passes'
AUTO_CAPTURE = 'a new node is included if it declares `schema`'
FAILURE_EVIDENCE = ['node_id', 'schema_id', 'schema_error_path', 'schema_error_message', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/tester/validators/test_contract_schema_compliance.py']


def test_contract_schema_conformance_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in schema archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
