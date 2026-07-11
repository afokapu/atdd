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

# Legacy parity oracle RETIRED (#1207): the legacy validator
# `test_plan_urn_resolution.py` was deleted once `both`-parity was proven
# (family-parity-report: resolution = 3/5 both; this variant is one of the three).
# LEGACY_PARITY_SOURCES kept as the provenance record.


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    """The variant returns no violations on the real, unmodified repo."""
    assert evaluate_variant(TEMPLATE, VARIANT, graph=clean_convention_graph) == []


def test_fault_injection() -> None:
    """Inject an unresolvable contract URN; the convention path (variant evaluator:
    produce-URN -> contracts/ dir) must catch it (legacy oracle retired, #1207)."""
    root = repo_root()
    with inject_patch(root, _WAGON_MANIFEST, *_FAULT):
        evidence = evaluate_variant(TEMPLATE, VARIANT, root=root)

    assert evidence, "convention path did not catch the unresolvable contract URN"
    for record in evidence:
        assert set(record).issubset(FAILURE_EVIDENCE), record
    assert evaluate_variant(TEMPLATE, VARIANT, root=root) == []
