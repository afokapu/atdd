# URN: test:validate-conventions:coherence-variants:train_family_matches_terminal_contract
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `coherence/train_family_matches_terminal_contract` (#1206).

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
VARIANT = "train_family_matches_terminal_contract"
QUESTION = 'After references resolve, do the resolved facts agree with each other?'
SELECTOR = 'nodes declaring coherence checks or semantic comparison rules'
TRAVERSAL = 'source node -> resolved fact A; source node -> resolved fact B; compare A and B'
INVARIANT = 'facts satisfy comparison predicate'
AUTO_CAPTURE = 'partial; a new node is included only if it declares a known coherence predicate'
FAILURE_EVIDENCE = ['source_node', 'fact_a', 'fact_b', 'predicate', 'actual_values']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_train_family_matches_terminal_contract.py']


def test_train_family_matches_terminal_contract_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in coherence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


# --- executable graph-question tests ---------------------------------------
# Clean baseline is 0 (only train 0002 declares a family, `behavior`, with a
# non-receipt terminal -> agrees). The fault (flip that train to family=delivery while
# its terminal is NOT a commit-receipt) is caught by the convention evaluator.


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    assert _parity.conv_violations(VARIANT, graph=clean_convention_graph) == []


def test_fault_injection(clean_convention_graph) -> None:
    """Flip a real train's family to disagree with its terminal artifact; the
    convention evaluator catches it. Injected into a deep clone of the session graph
    (#1416) — the train YAML is never rewritten and the shared graph is untouched.

    Legacy parity (verdict `both`) was proven against
    test_train_family_matches_terminal_contract.py::test_real_trains_family_matches_terminal_contract
    before that legacy validator was decommissioned (#1207);
    planner.train.family-matches-terminal-contract now binds its implementation.ref
    to this variant. The convention fault-injection is the live coverage."""
    train_id = next(
        t.id for t in clean_convention_graph.by_kind("train")
        if t.fields.get("family") == "behavior"
    )
    faulted = clone_graph(clean_convention_graph)
    set_node_field(faulted, train_id, "family", "delivery")

    conv = resolved_fact_agreement(faulted, {"variant": VARIANT})
    assert any(v["source_node"] == train_id for v in conv), (
        "convention evaluator did not catch the family/terminal disagreement"
    )
    # the shared clean graph still agrees (injection stayed on the clone)
    assert _parity.conv_violations(VARIANT, graph=clean_convention_graph) == []


def test_invalid_fragment_is_caught() -> None:
    out = resolved_fact_agreement(INVALID_FRAGMENTS[VARIANT], {"variant": VARIANT})
    assert len(out) == 1 and out[0]["fact_a"] == "delivery", out


def test_valid_fragment_is_clean() -> None:
    assert resolved_fact_agreement(VALID_FRAGMENTS[VARIANT], {"variant": VARIANT}) == []
