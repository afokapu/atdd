# URN: test:validate-conventions:presence-variants:rule_has_fix_hint
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `presence/rule_has_fix_hint` (#1206).

Instantiates the `presence/required_field_presence` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations


from atdd.validators.conventions.presence import archetype, fixtures
from atdd.validators.conventions.presence.archetype import TEMPLATE_IDS
from atdd.validators.conventions._support.graph_mutations import add_node, clone_graph

FAMILY = "presence"
TEMPLATE = "required_field_presence"
VARIANT = "rule_has_fix_hint"
QUESTION = 'Does every eligible node declare the fields required by its convention/schema?'
SELECTOR = 'nodes whose schema/kind declares required fields'
TRAVERSAL = 'node -> required_fields'
INVARIANT = 'every required field exists and is non-empty'
AUTO_CAPTURE = 'a new node is included if its schema/kind declares required fields'
FAILURE_EVIDENCE = ['node_id', 'missing_field', 'schema_id', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_fix_hint_completeness.py']


_TC = {t.template_id: t for t in archetype.TEMPLATES}

_EMPTY_HINT_RULE = "coach.tmp.empty-hint-probe"
_MALFORMED_HINT_RULE = "coach.tmp.malformed-hint-probe"


def _evaluate(graph) -> list:
    return _TC[TEMPLATE].evaluate(graph, {"variant": VARIANT})


def test_rule_has_fix_hint_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in presence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_rule_has_fix_hint_clean_baseline(clean_convention_graph) -> None:
    """Every fix_hint-declaring rule carries a non-empty value -> 0 violations."""
    assert _evaluate(clean_convention_graph) == []


def test_rule_has_fix_hint_fragment_catches_empty() -> None:
    """In-memory real-graph fragment: an empty fix_hint is caught, template-shaped."""
    valid = fixtures.VALID_FRAGMENTS[TEMPLATE][VARIANT]
    invalid = fixtures.INVALID_FRAGMENTS[TEMPLATE][VARIANT]
    assert _evaluate(valid) == []
    violations = _evaluate(invalid)
    assert violations, "fragment with an empty fix_hint not caught"
    for v in violations:
        assert set(v).issubset(set(FAILURE_EVIDENCE)), f"evidence not template-shaped: {set(v)}"


def test_rule_has_fix_hint_convention_fault(clean_convention_graph) -> None:
    """PARITY CLASSIFICATION: CONVENTION-ONLY (representation mismatch).

    The legacy validator (``test_fix_hint_completeness``) checks fix-hint
    COMPLETENESS (C1 placeholder-resolution / C2 deprecation) of hints that are
    PRESENT — it explicitly skips rules without a fix_hint. This convention variant
    checks PRESENCE-of-value. The two questions share NO faultable case, proven
    here in both directions.

    Both directions inject a rule NODE into a deep CLONE of the session graph (#1416):
    the same rule the on-disk ``rules:`` block used to add on rebuild, added straight to
    the clone. No convention YAML is written; the shared ``clean_convention_graph`` keeps
    its exact node set.
    """
    # Direction 1: an EMPTY fix_hint is caught (presence-of-value).
    empty = clone_graph(clean_convention_graph)
    add_node(empty, id=_EMPTY_HINT_RULE, kind="rule",
             fields={"rule_id": _EMPTY_HINT_RULE, "fix_hint": "   "})
    conv_empty = any(v["node_id"] == _EMPTY_HINT_RULE for v in _evaluate(empty))
    assert conv_empty, "convention did not catch the empty fix_hint (presence-of-value)"

    # Direction 2: a MALFORMED-but-present hint is OUT of scope (completeness was the
    # legacy's job, not this presence check) — the convention must NOT flag it.
    malformed = clone_graph(clean_convention_graph)
    add_node(malformed, id=_MALFORMED_HINT_RULE, kind="rule",
             fields={"rule_id": _MALFORMED_HINT_RULE, "fix_hint": "set the <thing> field"})
    conv_mal = any(v["node_id"] == _MALFORMED_HINT_RULE for v in _evaluate(malformed))
    assert not conv_mal, "convention should not flag a present-but-malformed hint (out of scope)"

    # the shared clean graph carried neither probe rule
    assert _EMPTY_HINT_RULE not in clean_convention_graph.ids()
    assert _MALFORMED_HINT_RULE not in clean_convention_graph.ids()
