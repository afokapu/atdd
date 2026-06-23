# URN: test:validate-conventions:grammar-variants:freedom_layer_bash_scope_grammar
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `grammar/freedom_layer_bash_scope_grammar` (#1206).

Instantiates the `grammar/identifier_grammar_conformance` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.grammar.archetype import TEMPLATE_IDS

FAMILY = "grammar"
TEMPLATE = "identifier_grammar_conformance"
VARIANT = "freedom_layer_bash_scope_grammar"
QUESTION = 'Does an identifier, URN, rule id, or node id follow canonical grammar?'
SELECTOR = 'nodes with id/rule_id/urn/name fields'
TRAVERSAL = 'node -> identifier field -> grammar parser'
INVARIANT = 'parser accepts identifier and parsed parts match graph context'
AUTO_CAPTURE = 'a new node is included if it declares a grammar-governed identifier field'
FAILURE_EVIDENCE = ['node_id', 'field', 'value', 'grammar_name', 'parse_error']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_e032_unit_002_validator_rejects_unscoped_bash_entry.py']


def test_freedom_layer_bash_scope_grammar_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in grammar archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
