# URN: test:validate-conventions:sizing-variants:wagon_coupling_complexity
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `sizing/wagon_coupling_complexity` (#1206).

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
    evaluate_coupling_complexity,
)

FAMILY = "sizing"
TEMPLATE = "cardinality_bounds"
VARIANT = "wagon_coupling_complexity"
QUESTION = 'Is the number of related nodes within allowed min/max bounds?'
SELECTOR = 'nodes or scopes with declared cardinality constraints'
TRAVERSAL = 'source/scope -> collect related nodes -> count'
INVARIANT = 'min <= count <= max'
AUTO_CAPTURE = 'a new node is included if it declares cardinality constraints'
FAILURE_EVIDENCE = ['source_node_or_scope', 'relationship', 'actual_count', 'min', 'max', 'targets']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_wagon_coupling_complexity.py']


_CONFIG = {"variant": VARIANT}
_TEMPLATE = TEMPLATES[0]
_TARGET_WAGON = "freeze-runtime-contracts"
_TARGET_FILE = "plan/freeze_runtime_contracts/_freeze_runtime_contracts.yaml"
# 7 artifacts each PRODUCED by a distinct other wagon — consuming all of them gives
# the target fan_in=7; it already has fan_out=9, so complexity 63 >> threshold 6.
_INJECT_CONSUMES = [
    "commons:admit:substrate-schemas", "commons:author:plan-spine",
    "commons:bind:lock-loader", "commons:coach:pr-watcher-module",
    "commons:coach:concurrent-wave-driver", "commons:coach:canonical-coach-surface",
    "commons:author:substrate-schemas",
]


def _norm(slug: str) -> str:
    return slug.replace("_", "-")


def test_wagon_coupling_complexity_variant_contract() -> None:
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
    """Real-graph fragments: VALID evaluates to [], INVALID to a non-empty finding."""
    cfg = F.FIXTURE_CONFIG[VARIANT]
    assert _TEMPLATE.evaluate(F.VALID_FRAGMENTS[VARIANT], cfg) == []
    assert _TEMPLATE.evaluate(F.INVALID_FRAGMENTS[VARIANT], cfg)


def test_clean_baseline_on_real_composed_graph(clean_convention_graph) -> None:
    """On the live repo no wagon exceeds the soft coupling threshold (no false positives)."""
    assert _TEMPLATE.evaluate(clean_convention_graph, _CONFIG) == []
    assert evaluate_coupling_complexity(clean_convention_graph) == []


def _inject_consumes(graph, rel, consumes):
    """Give the wagon loaded from `rel` a `consume` list, in a CLONE of the graph.

    `_wagon_io` reads the wagon's consume list straight out of `Node.fields`, so
    setting that field in memory is the same fault the on-disk rewrite of the wagon
    manifest produced — the file was only ever the delivery mechanism (#1458, E035).
    """
    wagon = node_at(graph, rel)
    return set_node_field(graph, wagon.id, "consume", [
        {"name": n, "contract": None, "telemetry": None, "from": "external"}
        for n in consumes
    ])


def _flagged(graph) -> set:
    return {_norm(ev["source_node_or_scope"].split(":", 1)[1])
            for ev in evaluate_coupling_complexity(graph)}


def test_fault_injection_legacy_parity(clean_convention_graph) -> None:
    """Inject an over-coupling fault into a cloned wagon node; assert the convention
    evaluator flags that wagon and that the shared session graph never saw the fault.

    The legacy in-process scan oracle was dropped with the retired legacy validator
    (#1207 sweep, #1385); the differential below is the live coverage. The fault is
    injected into a clone rather than the real wagon manifest (#1458, E035): the old
    mechanism rewrote `plan/.../_freeze_runtime_contracts.yaml`, rebuilt the graph,
    and reverted in a `finally`, costing two full graph builds and putting a plan YAML
    in the working tree for the duration.
    """
    graph = clone_graph(clean_convention_graph)
    _inject_consumes(graph, _TARGET_FILE, _INJECT_CONSUMES)

    assert _TARGET_WAGON in _flagged(graph), (
        f"convention missed injected fault: {_flagged(graph)}"
    )
    # Clone-independence replaces the old revert-and-rebuild: the session graph is the
    # SAME object every other test holds, so proving it is unflagged proves the
    # injection leaked nowhere.
    assert _TARGET_WAGON not in _flagged(clean_convention_graph), (
        "fault leaked out of the clone into the shared session graph"
    )
