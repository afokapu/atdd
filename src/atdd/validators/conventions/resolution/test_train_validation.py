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
from atdd.validators.conventions.resolution._parity import (
    evaluate_variant,
    inject_patch,
    legacy_caught,
    repo_root,
)

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
_TRAIN_FILE = "plan/_trains/0001-self-compliance-validate.yaml"
_FAULT = ('"wagon:validate-conventions"', '"wagon:does-not-exist-xyz"')
_LEGACY_NODEID = (
    "src/atdd/planner/validators/test_train_validation.py"
    "::test_train_wagon_references_exist_in_manifests"
)


def test_clean_baseline_is_zero() -> None:
    """The variant returns no violations on the real, unmodified repo."""
    assert evaluate_variant(TEMPLATE, VARIANT) == []


def test_fault_injection_and_legacy_parity() -> None:
    """Inject a dangling train->wagon reference; BOTH the convention path and the
    legacy validator must catch it (parity = both)."""
    root = repo_root()
    with inject_patch(root, _TRAIN_FILE, *_FAULT):
        evidence = evaluate_variant(TEMPLATE, VARIANT, root=root)
        legacy = legacy_caught(root, _LEGACY_NODEID)

    assert evidence, "convention path did not catch the dangling train->wagon ref"
    for record in evidence:
        assert set(record).issubset(FAILURE_EVIDENCE), record
    assert legacy, "legacy validator did not catch the injected fault"
    # revert guaranteed by inject_patch — clean baseline restored
    assert evaluate_variant(TEMPLATE, VARIANT, root=root) == []
