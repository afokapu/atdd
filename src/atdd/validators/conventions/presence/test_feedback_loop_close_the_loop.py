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

from pathlib import Path

from atdd.validators.conventions.presence import archetype, fixtures
from atdd.validators.conventions.presence.archetype import TEMPLATE_IDS
from atdd.validators.conventions._support.graph_loader import load_composed_graph

from .conftest import patched

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
# whose only close_the_loop SMOKE acceptance lives in WMBT P001.
P001_WMBT = "plan/observe_and_correct/P001.yaml"
_TARGET_FEATURE = "feature:observe-and-correct:observer-runtime-and-rules"


def _evaluate(graph) -> list:
    return _TC[TEMPLATE].evaluate(graph, {"variant": VARIANT})


def test_feedback_loop_close_the_loop_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in presence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_feedback_loop_clean_baseline(repo_root: Path) -> None:
    """Every non-suppressed feedback-loop feature has a close_the_loop SMOKE -> 0."""
    assert _evaluate(load_composed_graph(repo_root)) == []


def test_feedback_loop_fragment_catches_missing(repo_root: Path) -> None:
    """In-memory real-graph fragment: a feedback-loop feature whose WMBT lacks a
    close_the_loop SMOKE acceptance is caught; the with-block fragment is clean."""
    assert _evaluate(fixtures.VALID_FRAGMENTS[TEMPLATE][VARIANT]) == []
    violations = _evaluate(fixtures.INVALID_FRAGMENTS[TEMPLATE][VARIANT])
    assert violations, "fragment missing close_the_loop not caught"
    for v in violations:
        assert set(v).issubset(set(FAILURE_EVIDENCE)), f"evidence not template-shaped: {set(v)}"


def test_feedback_loop_catches_injected_fault(repo_root: Path) -> None:
    """Disabling the close_the_loop block on the real SMOKE acceptance is caught."""
    with patched(repo_root, P001_WMBT, "    close_the_loop:", "    close_the_loop_DISABLED:"):
        violations = _evaluate(load_composed_graph(repo_root))
    assert any(v["node_id"] == _TARGET_FEATURE for v in violations)


def test_feedback_loop_convention_fault(repo_root: Path) -> None:
    """The convention evaluator catches the injected fault (the feature's only
    close_the_loop SMOKE acceptance is disabled). Oracle retired (#1365)."""
    with patched(repo_root, P001_WMBT, "    close_the_loop:", "    close_the_loop_DISABLED:"):
        convention_caught = any(
            v["node_id"] == _TARGET_FEATURE for v in _evaluate(load_composed_graph(repo_root))
        )
    # oracle retired (#1365): the convention evaluator is the live coverage
    assert convention_caught, (
        f"convention evaluator did not catch the disabled close_the_loop SMOKE acceptance"
    )
