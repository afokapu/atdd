# URN: test:validate-conventions:presence-variants:rule_has_disposition
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `presence/rule_has_disposition` (#1206).

Instantiates the `presence/required_field_presence` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from pathlib import Path

from atdd.validators.conventions.presence import archetype
from atdd.validators.conventions.presence.archetype import TEMPLATE_IDS
from atdd.validators.conventions._support.graph_loader import load_composed_graph

from .conftest import patched

FAMILY = "presence"
TEMPLATE = "required_field_presence"
VARIANT = "rule_has_disposition"
QUESTION = 'Does every eligible node declare the fields required by its convention/schema?'
SELECTOR = 'nodes whose schema/kind declares required fields'
TRAVERSAL = 'node -> required_fields'
INVARIANT = 'every required field exists and is non-empty'
AUTO_CAPTURE = 'a new node is included if its schema/kind declares required fields'
FAILURE_EVIDENCE = ['node_id', 'missing_field', 'schema_id', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_rule_disposition_required.py']


_TC = {t.template_id: t for t in archetype.TEMPLATES}
# An enforceable rule (direct validator) whose disposition we drop to inject the
# fault. Its authoritative home is its single-node nodes/ file (#1225), so the
# fault is injected by dropping metadata.disposition there.
_TARGET_RULE = "planner.wmbt.must-have-smoke-acceptance"
WMBT_CONVENTION = (
    "src/atdd/planner/conventions/nodes/"
    "planner.wmbt.must-have-smoke-acceptance.convention.yaml"
)
_RULE_BLOCK = "  disposition: suppress-and-clean\n"
_RULE_BLOCK_NO_DISP = ""


def _evaluate(graph) -> list:
    return _TC[TEMPLATE].evaluate(graph, {"variant": VARIANT})


def test_rule_has_disposition_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in presence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_rule_has_disposition_clean_baseline(repo_root: Path) -> None:
    """Every allowlisted rule declares a legal disposition -> 0 violations."""
    assert _evaluate(load_composed_graph(repo_root)) == []


def test_rule_has_disposition_catches_injected_fault(repo_root: Path) -> None:
    """Dropping the disposition from an allowlisted rule is caught, template-shaped."""
    with patched(repo_root, WMBT_CONVENTION, _RULE_BLOCK, _RULE_BLOCK_NO_DISP):
        violations = _evaluate(load_composed_graph(repo_root))
    assert any(v["node_id"] == _TARGET_RULE for v in violations)
    for v in violations:
        assert set(v).issubset(set(FAILURE_EVIDENCE)), f"evidence not template-shaped: {set(v)}"
    # Legacy parity (verdict `both`) was proven against
    # test_rule_disposition_required.py::test_rule_disposition_required before that
    # legacy validator was decommissioned (#1207); coach.rule-id.disposition-required
    # now binds its implementation.ref to this variant. The clean-baseline +
    # fault-injection above are the live coverage.
