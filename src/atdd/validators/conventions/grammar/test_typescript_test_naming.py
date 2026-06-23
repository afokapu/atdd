# URN: test:validate-conventions:grammar-variants:typescript_test_naming
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `grammar/typescript_test_naming` (#1206).

Instantiates the `grammar/identifier_grammar_conformance` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.grammar.archetype import TEMPLATE_IDS

FAMILY = "grammar"
TEMPLATE = "identifier_grammar_conformance"
VARIANT = "typescript_test_naming"
QUESTION = 'Does an identifier, URN, rule id, or node id follow canonical grammar?'
SELECTOR = 'nodes with id/rule_id/urn/name fields'
TRAVERSAL = 'node -> identifier field -> grammar parser'
INVARIANT = 'parser accepts identifier and parsed parts match graph context'
AUTO_CAPTURE = 'a new node is included if it declares a grammar-governed identifier field'
FAILURE_EVIDENCE = ['node_id', 'field', 'value', 'grammar_name', 'parse_error']
LEGACY_PARITY_SOURCES = ['src/atdd/tester/validators/test_typescript_test_naming.py']


def test_typescript_test_naming_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in grammar archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
