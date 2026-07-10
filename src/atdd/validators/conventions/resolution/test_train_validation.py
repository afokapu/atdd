# URN: test:validate-conventions:resolution-variants:train_validation
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `resolution/train_validation` (#1206).

Instantiates the `resolution/direct_reference_resolution` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from atdd.validators.conventions.resolution.archetype import TEMPLATE_IDS
from atdd.validators.conventions.resolution._parity import evaluate_variant
from atdd.validators.conventions._support.graph_mutations import break_ref, clone_graph

FAMILY = "resolution"
TEMPLATE = "direct_reference_resolution"
VARIANT = "train_validation"
QUESTION = 'Does every declared reference resolve to an existing graph target?'
SELECTOR = 'nodes with refs/node_refs/rule_refs/relationship_targets'
TRAVERSAL = 'source node -> reference value -> target index'
INVARIANT = 'target_index.contains(reference)'
AUTO_CAPTURE = 'a new node is included if it declares references using standard ref fields'
FAILURE_EVIDENCE = ['source_node', 'ref_field', 'missing_ref', 'expected_target_kind', 'source_location']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_train_validation.py']


def test_train_validation_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in resolution archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


# Fault: a train participant pointing at a wagon that has no manifest.
_PARTICIPANT = "wagon:validate-conventions"
_BROKEN = "wagon:does-not-exist-xyz"


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    """The variant returns no violations on the real, unmodified repo."""
    assert evaluate_variant(TEMPLATE, VARIANT, graph=clean_convention_graph) == []


def test_fault_injection_and_legacy_parity(clean_convention_graph) -> None:
    """Inject a dangling train->wagon reference; the convention path must catch it.

    A real train's participant reference is repointed at a non-existent wagon on a deep
    clone of the session graph (#1416): the direct-reference evaluator flags the dangling
    ref exactly as the on-disk train-file rewrite made it, with nothing written to disk."""
    train_id = next(
        t.id for t in clean_convention_graph.by_kind("train")
        if _PARTICIPANT in t.refs
    )
    faulted = clone_graph(clean_convention_graph)
    break_ref(faulted, train_id, _PARTICIPANT, _BROKEN)

    evidence = evaluate_variant(TEMPLATE, VARIANT, graph=faulted)
    assert evidence, "convention path did not catch the dangling train->wagon ref"
    for record in evidence:
        assert set(record).issubset(FAILURE_EVIDENCE), record
    assert any(r.get("missing_ref") == _BROKEN for r in evidence), evidence
    # oracle retired (#1365): convention path above is the live coverage
    # the shared clean graph's train participants still resolve
    assert evaluate_variant(TEMPLATE, VARIANT, graph=clean_convention_graph) == []
