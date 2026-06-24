# URN: test:validate-conventions:resolution-variants:plan_urn_resolution
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `resolution/plan_urn_resolution` (#1206).

Instantiates the `resolution/artifact_reference_resolution` template against the composed convention
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
TEMPLATE = "artifact_reference_resolution"
VARIANT = "plan_urn_resolution"
QUESTION = 'Does every file, schema, fixture, or URN artifact reference resolve to a real artifact?'
SELECTOR = 'nodes with artifact_refs/file_refs/schema_refs/fixture_refs'
TRAVERSAL = 'node -> artifact reference -> repository artifact index'
INVARIANT = 'artifact exists and is addressable from repo root/package root'
AUTO_CAPTURE = 'a new node is included if it declares artifact references with standard metadata'
FAILURE_EVIDENCE = ['node_id', 'artifact_ref', 'artifact_kind', 'expected_path', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_plan_urn_resolution.py']


def test_plan_urn_resolution_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in resolution archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


# Fault: rewrite a produced contract URN's domain so neither the resource-level
# nor the domain-level contracts/ directory resolves. The govern_lifecycle wagon
# produces contract:commons:compliance:gate, which resolves on the clean repo.
_WAGON_MANIFEST = "plan/govern_lifecycle/_govern_lifecycle.yaml"
_FAULT = ("contract:commons:compliance:gate", "contract:zzznope:compliance:gate")
_LEGACY_NODEID = (
    "src/atdd/planner/validators/test_plan_urn_resolution.py"
    "::test_contract_urn_resolves_to_directory"
)


def test_clean_baseline_is_zero() -> None:
    """The variant returns no violations on the real, unmodified repo."""
    assert evaluate_variant(TEMPLATE, VARIANT) == []


def test_fault_injection_and_legacy_parity() -> None:
    """Inject an unresolvable contract URN; BOTH the convention path (variant
    evaluator: produce-URN -> contracts/ dir) and the legacy validator must catch
    it (parity = both)."""
    root = repo_root()
    with inject_patch(root, _WAGON_MANIFEST, *_FAULT):
        evidence = evaluate_variant(TEMPLATE, VARIANT, root=root)
        legacy = legacy_caught(root, _LEGACY_NODEID)

    assert evidence, "convention path did not catch the unresolvable contract URN"
    for record in evidence:
        assert set(record).issubset(FAILURE_EVIDENCE), record
    assert legacy, "legacy validator did not catch the injected fault"
    assert evaluate_variant(TEMPLATE, VARIANT, root=root) == []
