# URN: test:validate-conventions:binding-variants:validator_binding_bidirectional
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `binding/validator_binding_bidirectional` (#1206).

Instantiates the `binding/declaration_to_implementation_binding` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.binding.archetype import TEMPLATE_IDS

FAMILY = "binding"
TEMPLATE = "declaration_to_implementation_binding"
VARIANT = "validator_binding_bidirectional"
QUESTION = 'Does a declaration point to a real implementation, validator, or artifact that claims to enforce it?'
SELECTOR = 'rule/declaration nodes where enforcement requires implementation'
TRAVERSAL = 'declaration node -> implementation_ref -> implementation index'
INVARIANT = 'implementation exists and declares compatibility with the declaration'
AUTO_CAPTURE = 'a new node is included if it declares enforcement=validator or equivalent implementation binding metadata'
FAILURE_EVIDENCE = ['declaration_node', 'implementation_ref', 'missing_or_incompatible_implementation', 'declaration_location']
LEGACY_PARITY_SOURCES = ['src/atdd/tester/validators/test_repo_validator_binding.py']


def test_validator_binding_bidirectional_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in binding archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
