# URN: test:validate-conventions:schema-variants:dispatch_map_is_registry
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `schema/dispatch_map_is_registry` (#1206 / #1212).

Wires the variant onto the OFFICIAL execution path: the real composed convention
graph (`load_composed_graph`) dispatched through `TemplateContract.evaluate(graph,
config={"variant": "dispatch_map_is_registry"})`. The template asks the canonical
schema question — *does the declared `plan/_dispatch.yaml` registry conform to its
schema (`plan/_dispatch.schema.json`)* — and emits failure evidence that is a
subset of the template contract.

Legacy parity is measured against `planner/validators/test_dispatch_registry.py`
(same on-disk artifact + same schema): a single injected fault is run through BOTH
the convention path and the legacy validator (subprocess pytest); both must catch.
Imports no persona validator module, so it is parallel-safe with legacy validators.
"""
from __future__ import annotations

from pathlib import Path

from atdd.validators.conventions._support.graph_mutations import (
    graph_rooted_at,
    mirror_file,
)
from atdd.validators.conventions.schema.archetype import TEMPLATES, TEMPLATE_IDS

FAMILY = "schema"
TEMPLATE = "node_schema_conformance"
VARIANT = "dispatch_map_is_registry"
QUESTION = 'Does each node conform to its declared schema?'
SELECTOR = 'nodes where node.schema exists'
TRAVERSAL = 'node -> schema_id -> schema document -> validate node payload'
INVARIANT = 'jsonschema validation passes'
AUTO_CAPTURE = 'a new node is included if it declares `schema`'
FAILURE_EVIDENCE = ['node_id', 'schema_id', 'schema_error_path', 'schema_error_message', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_dispatch_registry.py']

# The schema-conformance counterpart in the legacy suite: same artifact, same schema.
_DISPATCH = "plan/_dispatch.yaml"
# Faulted registry: a dispatch entry missing the schema-required `train_id`.
_FAULT_ANCHOR = "dispatch: []"
_FAULT_REPLACEMENT = 'dispatch:\n  - artifact_urn: "x:y:z"\n'


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


def _contract():
    by_id = {t.template_id: t for t in TEMPLATES}
    return by_id[TEMPLATE]


def _evaluate(graph):
    """Run the variant through the official path on the composed graph."""
    return _contract().evaluate(graph, config={"variant": VARIANT})


# The variant reads BOTH the registry and its schema off `graph.root`, so a staged root
# must carry both — the schema unfaulted, the registry faulted (#1458, E035). There is
# no dispatch node to mutate: the evaluator yaml-loads the whole file and runs
# jsonschema over the raw document, so the fault has to be a real YAML it really parses.
_DISPATCH_SCHEMA = "plan/_dispatch.schema.json"


def _staged_faulted_registry(clean_graph, tmp_path):
    """Mirror the real registry + schema into `tmp_path`, faulting the registry."""
    root = _repo_root()
    mirror_file(root, tmp_path, _DISPATCH_SCHEMA)
    mirror_file(
        root, tmp_path, _DISPATCH,
        lambda t: t.replace(_FAULT_ANCHOR, _FAULT_REPLACEMENT, 1),
    )
    return graph_rooted_at(clean_graph, tmp_path)


# --- contract ---------------------------------------------------------------
def test_dispatch_map_is_registry_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in schema archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


# --- official-path execution + evidence shape -------------------------------
def test_evidence_keys_subset_of_contract(clean_convention_graph, tmp_path) -> None:
    """Whatever the variant emits, its evidence keys are a subset of the template
    contract's declared failure_evidence (proven via a faulted registry)."""
    allowed = set(FAILURE_EVIDENCE)
    ev = _evaluate(_staged_faulted_registry(clean_convention_graph, tmp_path))
    assert ev, "faulted registry produced no evidence"
    for rec in ev:
        assert set(rec).issubset(allowed), f"evidence keys escape contract: {set(rec) - allowed}"


# --- clean baseline ---------------------------------------------------------
def test_clean_baseline_is_silent(clean_convention_graph) -> None:
    """The real declared registry conforms to its schema → zero violations."""
    assert _evaluate(clean_convention_graph) == []


# --- fault injection (convention path is the live coverage; oracle retired #1365) ---
def test_fault_caught_by_convention(clean_convention_graph, tmp_path) -> None:
    """Inject one schema fault (entry missing `train_id`) into a staged copy of the
    registry; the convention path catches it and `plan/_dispatch.yaml` is never
    rewritten in the working tree."""
    staged = _staged_faulted_registry(clean_convention_graph, tmp_path)
    assert bool(_evaluate(staged)), "convention path missed the schema fault"
    assert _evaluate(clean_convention_graph) == [], "the real registry was written to"
