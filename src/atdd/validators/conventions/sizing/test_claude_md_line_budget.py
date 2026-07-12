# URN: test:validate-conventions:sizing-variants:claude_md_line_budget
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `sizing/claude_md_line_budget` (#1206).

Instantiates the `sizing/cardinality_bounds` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.sizing.archetype import TEMPLATE_IDS

FAMILY = "sizing"
TEMPLATE = "cardinality_bounds"
VARIANT = "claude_md_line_budget"
QUESTION = 'Is the number of related nodes within allowed min/max bounds?'
SELECTOR = 'nodes or scopes with declared cardinality constraints'
TRAVERSAL = 'source/scope -> collect related nodes -> count'
INVARIANT = 'min <= count <= max'
AUTO_CAPTURE = 'a new node is included if it declares cardinality constraints'
FAILURE_EVIDENCE = ['source_node_or_scope', 'relationship', 'actual_count', 'min', 'max', 'targets']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_e023_smoke_001_live_claude_md_line_count_within_budget.py', 'src/atdd/coach/validators/test_e023_unit_001_claude_md_is_at_most_250_lines.py', 'src/atdd/coach/validators/test_r002_smoke_001_atdd_validate_coach_includes_size_budget_rule.py', 'src/atdd/coach/validators/test_r002_unit_001_validator_fails_when_claude_md_exceeds_budget.py', 'src/atdd/coach/validators/test_r002_unit_002_validator_passes_when_claude_md_within_budget.py']


def test_claude_md_line_budget_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in sizing archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
