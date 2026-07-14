# URN: test:validate-conventions:resolution-variants:draft_wagon_registry
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `resolution/draft_wagon_registry` (#1206).

Instantiates the `resolution/artifact_reference_resolution` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from pathlib import Path

from atdd.validators.conventions.resolution.archetype import TEMPLATE_IDS
from atdd.validators.conventions.resolution._parity import (
    evaluate_variant,
    repo_root,
)
from atdd.validators.conventions._support.graph_mutations import (
    graph_rooted_at,
    mirror_file,
)

FAMILY = "resolution"
TEMPLATE = "artifact_reference_resolution"
VARIANT = "draft_wagon_registry"
QUESTION = 'Does every file, schema, fixture, or URN artifact reference resolve to a real artifact?'
SELECTOR = 'nodes with artifact_refs/file_refs/schema_refs/fixture_refs'
TRAVERSAL = 'node -> artifact reference -> repository artifact index'
INVARIANT = 'artifact exists and is addressable from repo root/package root'
AUTO_CAPTURE = 'a new node is included if it declares artifact references with standard metadata'
FAILURE_EVIDENCE = ['node_id', 'artifact_ref', 'artifact_kind', 'expected_path', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_draft_wagon_registry.py']


def test_draft_wagon_registry_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in resolution archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


# Fault: rewrite a registry consume `from: wagon:<slug>` to a wagon that is not
# present in plan/_wagons.yaml (phantom reference).
_REGISTRY = "plan/_wagons.yaml"
_FAULT = ("from: wagon:freeze-runtime-contracts", "from: wagon:does-not-exist-xyz")


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    """The variant returns no violations on the real, unmodified repo."""
    assert evaluate_variant(TEMPLATE, VARIANT, graph=clean_convention_graph) == []


def test_fault_injection(clean_convention_graph, tmp_path: Path) -> None:
    """Inject a phantom registry consume->wagon reference; the convention path
    (variant evaluator: registry consume.from -> registry slug set) must catch it.

    Staged, not written (#1458): ``_draft_wagon_registry`` reads ``plan/_wagons.yaml``
    through ``graph.root`` and reads no node, so mirroring that one file with the phantom
    ref and re-rooting a copy of the session graph at the temp tree runs the identical
    evaluator over the real registry's own bytes — without touching the checkout, and
    without a graph rebuild.

    Non-vacuity is structural on both ends: ``mirror_file`` raises if the fault anchor has
    drifted out of the real registry, and the evaluator returns [] outright when the
    registry is absent, so an empty staged tree could not satisfy the assertion below.
    """
    # Legacy parity (verdict 'both') was proven against the legacy validator before
    # it was decommissioned (#1207); the convention fault-injection is the live coverage.
    mirror_file(repo_root(), tmp_path, _REGISTRY, lambda t: t.replace(*_FAULT, 1))
    evidence = evaluate_variant(
        TEMPLATE, VARIANT, graph=graph_rooted_at(clean_convention_graph, tmp_path)
    )

    assert evidence, "convention path did not catch the phantom registry consume ref"
    for record in evidence:
        assert set(record).issubset(FAILURE_EVIDENCE), record
    # The untouched session graph stays clean: the phantom ref exists only in the temp tree.
    assert evaluate_variant(TEMPLATE, VARIANT, graph=clean_convention_graph) == []
