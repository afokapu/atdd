# URN: test:validate-conventions:resolution-variants:urn_traceability
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `resolution/urn_traceability` (#1206).

Instantiates the `resolution/reference_chain_resolution` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.resolution.archetype import TEMPLATE_IDS
from atdd.validators.conventions.resolution._parity import evaluate_variant
from atdd.validators.conventions._support.graph_mutations import break_ref, clone_graph

FAMILY = "resolution"
TEMPLATE = "reference_chain_resolution"
VARIANT = "urn_traceability"
QUESTION = 'Does a multi-hop reference chain resolve completely?'
SELECTOR = 'nodes that declare chained references or transitive dependencies'
TRAVERSAL = 'start node -> ref A -> target node -> ref B -> final target'
INVARIANT = 'all hops resolve; no missing intermediate target'
AUTO_CAPTURE = 'a new node is included if it declares a chain shape using standard traversal metadata'
FAILURE_EVIDENCE = ['start_node', 'chain_path', 'failed_hop', 'missing_ref']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_urn_traceability.py']


def test_urn_traceability_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in resolution archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


# Fault: break a wagon->feature URN hop so the multi-hop chain dead-ends.
_FEATURE_URN = "feature:admit-substrate:substrate-admission"
_BROKEN_URN = f"{_FEATURE_URN}-does-not-exist-xyz"


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    """The variant returns no violations on the real, unmodified repo."""
    assert evaluate_variant(TEMPLATE, VARIANT, graph=clean_convention_graph) == []


def test_fault_injection_convention_catches(clean_convention_graph) -> None:
    """Inject a broken wagon->feature chain hop; the convention path must catch it.

    The wagon's outgoing feature reference is repointed at a non-existent URN on a deep
    clone of the session graph (#1416): the chain dead-ends at hop 1 exactly as the on-disk
    manifest rewrite made it, with no file written and the shared graph untouched."""
    wagon_id = next(
        w.id for w in clean_convention_graph.by_kind("wagon")
        if _FEATURE_URN in w.refs
    )
    faulted = clone_graph(clean_convention_graph)
    break_ref(faulted, wagon_id, _FEATURE_URN, _BROKEN_URN)

    evidence = evaluate_variant(TEMPLATE, VARIANT, graph=faulted)
    assert evidence, "convention path did not catch the broken URN chain"
    for record in evidence:
        assert set(record).issubset(FAILURE_EVIDENCE), record
    assert any(r.get("missing_ref") == _BROKEN_URN for r in evidence), evidence
    # the shared clean graph's chain still resolves
    assert evaluate_variant(TEMPLATE, VARIANT, graph=clean_convention_graph) == []


# Legacy-vacuity cross-check removed (#1365): the legacy coach validator (which
# self-suppressed every finding via pytest.skip, making this a convention-only
# improvement) is being decommissioned. The variant's own real-graph fault
# injection above (`test_fault_injection_convention_catches`) is the live coverage.
