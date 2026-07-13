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


from atdd.validators.conventions.presence import archetype, fixtures
from atdd.validators.conventions.presence.archetype import TEMPLATE_IDS
from atdd.validators.conventions._support.graph_mutations import (
    clone_graph,
    set_node_field,
)

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


_TC = {t.template_id: t for t in archetype.TEMPLATES}
# observe-and-correct:observer-runtime-and-rules is the live feedback-loop feature
# whose only close_the_loop SMOKE acceptance lives in WMBT P001. Clearing that WMBT's
# acceptances on the clone removes the feature's only close_the_loop SMOKE, so the
# conditional-requirement evaluator flags the feature — the same outcome the on-disk
# ``close_the_loop:`` rename produced, with nothing written to disk.
_P001 = "wmbt:observe-and-correct:P001"
_TARGET_FEATURE = "feature:observe-and-correct:observer-runtime-and-rules"


def _fault(clean):
    faulted = clone_graph(clean)
    set_node_field(faulted, _P001, "acceptances", [])
    return faulted


def _evaluate(graph) -> list:
    return _TC[TEMPLATE].evaluate(graph, {"variant": VARIANT})


def test_feedback_loop_close_the_loop_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in presence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_feedback_loop_clean_baseline(clean_convention_graph) -> None:
    """Every non-suppressed feedback-loop feature has a close_the_loop SMOKE -> 0."""
    assert _evaluate(clean_convention_graph) == []


def test_feedback_loop_fragment_catches_missing() -> None:
    """In-memory real-graph fragment: a feedback-loop feature whose WMBT lacks a
    close_the_loop SMOKE acceptance is caught; the with-block fragment is clean."""
    assert _evaluate(fixtures.VALID_FRAGMENTS[TEMPLATE][VARIANT]) == []
    violations = _evaluate(fixtures.INVALID_FRAGMENTS[TEMPLATE][VARIANT])
    assert violations, "fragment missing close_the_loop not caught"
    for v in violations:
        assert set(v).issubset(set(FAILURE_EVIDENCE)), f"evidence not template-shaped: {set(v)}"


def test_feedback_loop_catches_injected_fault(clean_convention_graph) -> None:
    """Disabling the feature's only close_the_loop SMOKE acceptance is caught (#1416).

    Injected into a deep clone of the session graph — no disk write."""
    violations = _evaluate(_fault(clean_convention_graph))
    assert any(v["node_id"] == _TARGET_FEATURE for v in violations)
    # the shared clean graph still satisfies the requirement
    assert _evaluate(clean_convention_graph) == []


def test_feedback_loop_convention_fault(clean_convention_graph) -> None:
    """The convention evaluator catches the injected fault (the feature's only
    close_the_loop SMOKE acceptance is disabled). Oracle retired (#1365)."""
    convention_caught = any(
        v["node_id"] == _TARGET_FEATURE for v in _evaluate(_fault(clean_convention_graph))
    )
    # oracle retired (#1365): the convention evaluator is the live coverage
    assert convention_caught, (
        "convention evaluator did not catch the disabled close_the_loop SMOKE acceptance"
    )
