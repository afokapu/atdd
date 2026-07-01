# URN: test:validate-conventions:uniqueness-variants:plan_uniqueness
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `uniqueness/plan_uniqueness` (#1206).

Instantiates the `uniqueness/scoped_identifier_uniqueness` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.uniqueness.archetype import TEMPLATE_IDS

FAMILY = "uniqueness"
TEMPLATE = "scoped_identifier_uniqueness"
VARIANT = "plan_uniqueness"
QUESTION = 'Within a declared scope, does each identifier appear only once?'
SELECTOR = 'nodes grouped by identity_scope'
TRAVERSAL = 'scope -> collect node ids -> count occurrences'
INVARIANT = 'count(id) == 1 within scope'
AUTO_CAPTURE = 'a new node is included if it declares an id and identity scope'
FAILURE_EVIDENCE = ['duplicate_id', 'scope', 'locations', 'node_kinds']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_plan_uniqueness.py']


def test_plan_uniqueness_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in uniqueness archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
