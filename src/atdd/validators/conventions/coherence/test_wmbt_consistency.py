# URN: test:validate-conventions:coherence-variants:wmbt_consistency
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `coherence/wmbt_consistency` (#1206).

Instantiates the `coherence/resolved_fact_agreement` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.coherence import _parity
from atdd.validators.conventions.coherence.archetype import (
    TEMPLATE_IDS,
    resolved_fact_agreement,
)
from atdd.validators.conventions.coherence.fixtures import (
    INVALID_FRAGMENTS,
    VALID_FRAGMENTS,
)
from atdd.validators.conventions._support.graph_mutations import (
    clone_graph,
    set_node_field,
)

FAMILY = "coherence"
TEMPLATE = "resolved_fact_agreement"
VARIANT = "wmbt_consistency"
QUESTION = 'After references resolve, do the resolved facts agree with each other?'
SELECTOR = 'nodes declaring coherence checks or semantic comparison rules'
TRAVERSAL = 'source node -> resolved fact A; source node -> resolved fact B; compare A and B'
INVARIANT = 'facts satisfy comparison predicate'
AUTO_CAPTURE = 'partial; a new node is included only if it declares a known coherence predicate'
FAILURE_EVIDENCE = ['source_node', 'fact_a', 'fact_b', 'predicate', 'actual_values']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_wmbt_consistency.py']


def test_wmbt_consistency_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in coherence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


# --- executable graph-question tests ---------------------------------------
# Clean baseline is 0 (every wagon's manifest WMBT declarations agree with its on-disk
# WMBT files). The fault (declare a phantom WMBT code Z999 in a manifest with no matching
# file) is caught by the convention evaluator.
_FAULT_WAGON = "validate-conventions"
_PHANTOM_CODE = "Z999"


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    assert _parity.conv_violations(VARIANT, graph=clean_convention_graph) == []


def test_fault_injection(clean_convention_graph) -> None:
    """Declare a phantom WMBT code with no file in a real wagon manifest; assert the
    convention evaluator catches it. Injected into a deep clone of the session graph
    (#1416): the ``wmbt`` mapping of the wagon node gains a phantom code in memory, so the
    manifest-vs-filesystem disagreement fires — nothing is written to disk."""
    # Legacy parity (verdict 'both') was proven against the legacy validator before
    # it was decommissioned (#1207); the convention fault-injection is the live coverage.
    wagon_id = next(
        w.id for w in clean_convention_graph.by_kind("wagon")
        if w.fields.get("wagon") == _FAULT_WAGON
    )
    faulted = clone_graph(clean_convention_graph)
    set_node_field(faulted, wagon_id, ("wmbt", _PHANTOM_CODE), "phantom wmbt with no file")

    conv = resolved_fact_agreement(faulted, {"variant": VARIANT})
    assert any(
        v["source_node"] == wagon_id and _PHANTOM_CODE in v["actual_values"]["declared_only"]
        for v in conv
    ), "convention evaluator did not catch the phantom WMBT declaration"
    # the shared clean graph's manifest still agrees with its files
    assert _parity.conv_violations(VARIANT, graph=clean_convention_graph) == []


def test_invalid_fragment_is_caught() -> None:
    out = resolved_fact_agreement(INVALID_FRAGMENTS[VARIANT], {"variant": VARIANT})
    assert len(out) == 1 and out[0]["actual_values"]["declared_only"] == ["E999"], out


def test_valid_fragment_is_clean() -> None:
    assert resolved_fact_agreement(VALID_FRAGMENTS[VARIANT], {"variant": VARIANT}) == []
