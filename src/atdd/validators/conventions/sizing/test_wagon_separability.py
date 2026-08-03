# URN: test:validate-conventions:sizing-variants:wagon_separability
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `sizing/wagon_separability` (#1206).

Instantiates the `sizing/cardinality_bounds` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions._support.graph_mutations import (
    clone_graph,
    node_at,
    set_node_field,
)
from atdd.validators.conventions.sizing import fixtures as F
from atdd.validators.conventions.sizing.archetype import (
    TEMPLATE_IDS,
    TEMPLATES,
    evaluate_separability,
)

FAMILY = "sizing"
TEMPLATE = "cardinality_bounds"
VARIANT = "wagon_separability"
QUESTION = 'Is the number of related nodes within allowed min/max bounds?'
SELECTOR = 'nodes or scopes with declared cardinality constraints'
TRAVERSAL = 'source/scope -> collect related nodes -> count'
INVARIANT = 'min <= count <= max'
AUTO_CAPTURE = 'a new node is included if it declares cardinality constraints'
FAILURE_EVIDENCE = ['source_node_or_scope', 'relationship', 'actual_count', 'min', 'max', 'targets']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_wagon_separability.py']


_CONFIG = {"variant": VARIANT}
_TEMPLATE = TEMPLATES[0]
_TARGET_WAGON = "integrate-end-to-end"  # currently separable; flipped by injection below
# Inject into the target's 3 WMBTs token-sets borrowed from 3 distinct members of a
# neighbor wagon. The sets are mutually disjoint (=> 0 internal cohesion) and each
# pairs with its neighbor member (=> cross-coupling), so the target flips to [MERGE].
_INJECT = {
    "plan/integrate_end_to_end/D001.yaml": "anti convention define",
    "plan/integrate_end_to_end/E001.yaml": "calls code concatenation",
    "plan/integrate_end_to_end/M001.yaml": "auth authenticated dependency",
}


def test_wagon_separability_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in sizing archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_evidence_keys_subset_of_contract() -> None:
    """Every evidence dict's keys are a SUBSET of the template's failure_evidence."""
    allowed = set(FAILURE_EVIDENCE)
    findings = _TEMPLATE.evaluate(F.INVALID_FRAGMENTS[VARIANT], F.FIXTURE_CONFIG[VARIANT])
    assert findings
    for ev in findings:
        assert set(ev) <= allowed, f"evidence keys {set(ev)} escape contract {allowed}"


def test_fixture_fragments_valid_clean_invalid_flagged() -> None:
    """Real-graph fragments: VALID (cohesive wagon) -> [], INVALID (0-cohesion wagon
    coupled to a neighbor) -> a non-empty [MERGE] finding."""
    cfg = F.FIXTURE_CONFIG[VARIANT]
    assert _TEMPLATE.evaluate(F.VALID_FRAGMENTS[VARIANT], cfg) == []
    assert _TEMPLATE.evaluate(F.INVALID_FRAGMENTS[VARIANT], cfg)


def _flagged(graph) -> set:
    return {ev["source_node_or_scope"].split(":", 1)[1]
            for ev in evaluate_separability(graph)}


def test_live_corpus_legacy_parity(clean_convention_graph) -> None:
    """HONESTY NOTE: separability is an ADVISORY metric that genuinely fires on the
    valid live corpus (non-separable wagons are a real advisory signal, NOT false
    positives), so a clean baseline of [] is NOT the right invariant here.

    Parity against the legacy scan was proven and recorded (#1212); the legacy in-process
    oracle was dropped with the retired legacy validator (#1207 sweep, #1385). What this
    test still pins on the live graph is that the evaluator RUNS, surfaces findings, and
    is deterministic. The real differential — a wagon flipped non-separable is caught —
    lives in ``test_fault_injection_legacy_parity`` below.

    Determinism is asserted over the session graph evaluated twice (#1458, E035). What
    is under test is the EVALUATOR's determinism — it iterates dicts and sets and could
    order-depend — not the loader's, and re-composing the same unchanged tree twice to
    check that cost two full graph builds to re-derive an input already in hand.
    """
    conv = _flagged(clean_convention_graph)
    assert conv, "advisory metric expected to surface findings on the live corpus"

    again = _flagged(clean_convention_graph)
    assert conv == again, f"evaluator is non-deterministic on the live graph: {conv ^ again}"


def _inject_tokens(graph, mapping):
    """Rewrite each named WMBT's salient-token fields, in a CLONE of the graph.

    `_wmbts_by_wagon` derives its tokens from `object_of_control` + `statement` on the
    WMBT nodes, so setting those two fields in memory is the same fault the on-disk
    rewrite of the three WMBT YAMLs produced (#1458, E035).
    """
    for rel, text in mapping.items():
        wmbt = node_at(graph, rel)
        set_node_field(graph, wmbt.id, "object_of_control", text)
        set_node_field(graph, wmbt.id, "statement", text)


def test_fault_injection_legacy_parity(clean_convention_graph) -> None:
    """Flip a currently-separable wagon to non-separable by rewriting its WMBTs' tokens
    in a cloned graph; assert the convention evaluator flags it and that the shared
    session graph never saw the fault.

    The legacy in-process scan oracle was dropped with the retired legacy validator
    (#1207 sweep, #1385); this differential is the live coverage. The old mechanism
    rewrote three real plan YAMLs and rebuilt the graph twice (#1458, E035).
    """
    graph = clone_graph(clean_convention_graph)
    _inject_tokens(graph, _INJECT)

    assert _TARGET_WAGON in _flagged(graph), (
        f"convention missed injected fault: {_flagged(graph)}"
    )
    assert _TARGET_WAGON not in _flagged(clean_convention_graph), (
        "fault leaked out of the clone into the shared session graph"
    )
