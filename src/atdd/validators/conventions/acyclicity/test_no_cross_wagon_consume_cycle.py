# URN: test:validate-conventions:acyclicity-variants:no_cross_wagon_consume_cycle
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `acyclicity/no_cross_wagon_consume_cycle` (#1206).

Instantiates the `acyclicity/forbidden_cycle_absence` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.validators.conventions.acyclicity import archetype, fixtures
from atdd.validators.conventions.acyclicity.archetype import (
    TEMPLATE_IDS,
    TEMPLATES,
    build_consume_edges,
    forbidden_cycle_absence,
)
from atdd.validators.conventions._support.graph_loader import load_composed_graph
from atdd.validators.conventions.acyclicity import _parity

FAMILY = "acyclicity"
TEMPLATE = "forbidden_cycle_absence"
VARIANT = "no_cross_wagon_consume_cycle"
QUESTION = 'Does a traversal avoid cycles where cycles are forbidden?'
SELECTOR = 'edge types or relationship subgraphs marked acyclic'
TRAVERSAL = 'nodes -> selected edge type/path -> depth-first traversal'
INVARIANT = 'no node appears twice in the same traversal path'
AUTO_CAPTURE = 'a new node is included if it participates in an edge type declared acyclic'
FAILURE_EVIDENCE = ['cycle_path', 'edge_type', 'start_node', 'repeated_node']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_no_cross_wagon_consume_cycle.py']




def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")






def test_no_cross_wagon_consume_cycle_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in acyclicity archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


# --- fixture-fragment execution (real ConventionGraph fragments) ------------
def test_valid_fragment_has_no_cycle() -> None:
    g = fixtures.VALID_FRAGMENTS["acyclic_chain"]()
    assert forbidden_cycle_absence(g) == []


def test_invalid_fragment_is_caught_with_subset_evidence() -> None:
    g = fixtures.INVALID_FRAGMENTS["two_wagon_cycle"]()
    out = forbidden_cycle_absence(g)
    assert len(out) == 1, f"expected exactly one cross-wagon cycle, got {out}"
    ev = out[0]
    assert set(ev).issubset(set(FAILURE_EVIDENCE)), \
        f"evidence keys {set(ev)} not a subset of {FAILURE_EVIDENCE}"
    assert ev["edge_type"] == "produce->consume"
    assert set(fixtures.cycle_members(None)).issubset(set(ev["cycle_path"]))


def test_template_evaluate_dispatches_to_real_evaluator() -> None:
    """TemplateContract.evaluate routes a ConventionGraph to this family's
    REAL_EVALUATORS entry (auto-discovered, no edit to _support)."""
    tmpl = TEMPLATES[0]
    assert tmpl.evaluate(fixtures.VALID_FRAGMENTS["acyclic_chain"]()) == []
    assert len(tmpl.evaluate(fixtures.INVALID_FRAGMENTS["two_wagon_cycle"]())) == 1


# --- clean baseline on the REAL composed graph ------------------------------
def test_clean_baseline_real_graph_is_zero() -> None:
    """The real repo's produce/consume wagon graph is a DAG (baseline = 0), and
    the selection is non-vacuous (there ARE cross-wagon produce/consume edges)."""
    repo_root = _repo_root()
    g = load_composed_graph(repo_root)
    edges = build_consume_edges(g)
    total_cross_edges = sum(len(v) for v in edges.values())
    assert total_cross_edges > 0, "vacuous: no cross-wagon produce/consume edges in corpus"
    assert forbidden_cycle_absence(g) == [], "real corpus unexpectedly has a cross-wagon cycle"


# --- fault injection (convention path is the live coverage; oracle retired #1365) ---
def test_fault_injection_convention_catches() -> None:
    repo_root = _repo_root()
    with _parity.injected_cross_wagon_cycle(repo_root) as members:
        conv = forbidden_cycle_absence(load_composed_graph(repo_root))
    conv_caught = any(set(members).issubset(set(v["cycle_path"])) for v in conv)
    assert conv_caught, (
        "convention path did not catch the injected cross-wagon cycle"
    )
