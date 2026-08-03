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
from atdd.validators.conventions._support.graph_mutations import (
    graph_rooted_at,
    mirror_file,
)

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


def test_phase_machine_init_gate_clean_baseline(clean_convention_graph) -> None:
    """INIT declares a pre_commit_gate invoking the planner validator -> 0 violations."""
    assert _evaluate(clean_convention_graph) == []


def _staged_broken_gate(repo_root: Path, tmp_path: Path, graph):
    """Mirror the phase-machine convention with a gate that no longer runs the planner
    validator, and hand back a graph rooted at that staged tree.

    The evaluator reads this convention through ``graph.root`` and nothing else (see
    ``presence.archetype._check_phase_machine_init_precommit_gate``), so redirecting the
    root at a tree holding the faulted file exercises the identical code path against the
    real file's own bytes — with the checkout never written. ``mirror_file`` raises if the
    ``_GATE_OK`` anchor has drifted out of the real convention, so the fault can never go
    vacuous.
    """
    mirror_file(repo_root, tmp_path, PHASE_MACHINE_CONVENTION,
                lambda t: t.replace(_GATE_OK, _GATE_BROKEN, 1))
    return graph_rooted_at(graph, tmp_path)


def test_phase_machine_init_gate_catches_injected_fault(
    clean_convention_graph, repo_root: Path, tmp_path: Path
) -> None:
    """A gate that no longer invokes the planner validator is caught, template-shaped."""
    violations = _evaluate(_staged_broken_gate(repo_root, tmp_path, clean_convention_graph))
    caught = [v for v in violations if v["node_id"] == "phase_machine.phases.INIT"]
    assert caught, f"the staged pre_commit_gate fault was not caught: {violations}"
    # NON-VACUITY: an EMPTY staged tree would also yield a violation here — the `missing_field`
    # would just read "pre_commit_gate". Requiring the "must invoke" wording proves the
    # evaluator actually parsed the staged convention and found INIT's gate present but
    # wrong, which is the fault, rather than finding no file at all.
    assert "must invoke" in caught[0]["missing_field"], (
        f"evidence says the gate is absent, not wrong — the staged tree may be empty: {caught[0]}"
    )
    for v in violations:
        assert set(v).issubset(set(FAILURE_EVIDENCE)), f"evidence not template-shaped: {set(v)}"


def test_phase_machine_init_gate_fault_injection(
    clean_convention_graph, repo_root: Path, tmp_path: Path
) -> None:
    """One injected fault (INIT.pre_commit_gate no longer runs ``atdd validate planner``)
    is caught by the convention evaluator, and the real convention is NOT the one faulted."""
    # Legacy parity (verdict 'both') was proven against the legacy validator before it
    # was decommissioned (#1207); the convention fault-injection is the live coverage.
    staged = _staged_broken_gate(repo_root, tmp_path, clean_convention_graph)
    assert _evaluate(staged), "convention failed to catch the injected pre_commit_gate fault"
    # The same evaluator over the untouched session graph stays silent — proof the fault
    # lives only in the staged tree and the shared graph's root was not redirected.
    assert _evaluate(clean_convention_graph) == []
