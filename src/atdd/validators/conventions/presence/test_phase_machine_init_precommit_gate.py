# URN: test:validate-conventions:presence-variants:phase_machine_init_precommit_gate
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `presence/phase_machine_init_precommit_gate` (#1206).

Instantiates the `presence/required_field_presence` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from pathlib import Path

from atdd.validators.conventions.presence import archetype
from atdd.validators.conventions.presence.archetype import TEMPLATE_IDS
from atdd.validators.conventions._support.graph_loader import load_composed_graph

from .conftest import patched

FAMILY = "presence"
TEMPLATE = "required_field_presence"
VARIANT = "phase_machine_init_precommit_gate"
QUESTION = 'Does every eligible node declare the fields required by its convention/schema?'
SELECTOR = 'nodes whose schema/kind declares required fields'
TRAVERSAL = 'node -> required_fields'
INVARIANT = 'every required field exists and is non-empty'
AUTO_CAPTURE = 'a new node is included if its schema/kind declares required fields'
FAILURE_EVIDENCE = ['node_id', 'missing_field', 'schema_id', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_phase_machine_init_pre_commit_gate.py']


_TC = {t.template_id: t for t in archetype.TEMPLATES}
PHASE_MACHINE_CONVENTION = "src/atdd/coach/conventions/phase_machine.convention.yaml"
_GATE_OK = 'pre_commit_gate: "atdd validate planner --local --skip-api"'
_GATE_BROKEN = 'pre_commit_gate: "echo nope"'


def _evaluate(graph) -> list:
    return _TC[TEMPLATE].evaluate(graph, {"variant": VARIANT})


def test_phase_machine_init_precommit_gate_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in presence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_phase_machine_init_gate_clean_baseline(repo_root: Path) -> None:
    """INIT declares a pre_commit_gate invoking the planner validator -> 0 violations."""
    assert _evaluate(load_composed_graph(repo_root)) == []


def test_phase_machine_init_gate_catches_injected_fault(repo_root: Path) -> None:
    """A gate that no longer invokes the planner validator is caught, template-shaped."""
    with patched(repo_root, PHASE_MACHINE_CONVENTION, _GATE_OK, _GATE_BROKEN):
        violations = _evaluate(load_composed_graph(repo_root))
    assert any(v["node_id"] == "phase_machine.phases.INIT" for v in violations)
    for v in violations:
        assert set(v).issubset(set(FAILURE_EVIDENCE)), f"evidence not template-shaped: {set(v)}"


def test_phase_machine_init_gate_fault_injection(repo_root: Path) -> None:
    """One injected fault (INIT.pre_commit_gate no longer runs ``atdd validate planner``)
    is caught by the convention evaluator."""
    # Legacy parity (verdict 'both') was proven against the legacy validator before it
    # was decommissioned (#1207); the convention fault-injection is the live coverage.
    with patched(repo_root, PHASE_MACHINE_CONVENTION, _GATE_OK, _GATE_BROKEN):
        convention_caught = bool(_evaluate(load_composed_graph(repo_root)))
    assert convention_caught, f"convention failed to catch fault: convention_caught={convention_caught}"
