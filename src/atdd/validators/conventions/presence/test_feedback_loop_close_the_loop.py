# URN: test:validate-conventions:presence-variants:feedback_loop_close_the_loop
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `presence/feedback_loop_close_the_loop` (#1206).

Instantiates the `presence/conditional_requirement` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.presence.archetype import TEMPLATE_IDS

FAMILY = "presence"
TEMPLATE = "conditional_requirement"
VARIANT = "feedback_loop_close_the_loop"
QUESTION = 'If condition A is true on a node, does field/edge B exist?'
SELECTOR = 'nodes declaring conditional requirements'
TRAVERSAL = 'node -> condition field/value -> required field/edge'
INVARIANT = 'if condition is true, required target exists'
AUTO_CAPTURE = 'a new node is included if its schema declares conditional requirements'
FAILURE_EVIDENCE = ['node_id', 'condition', 'missing_requirement', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_feedback_loop_smoke_closes_the_loop.py']


def test_feedback_loop_close_the_loop_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in presence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
