# URN: test:validate-conventions:coverage-variants:hierarchy_coverage
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `coverage/hierarchy_coverage` (#1206 / #1212).

Instantiates the `coverage/source_has_required_target` template against the composed convention
graph (real `Node` objects). Bidirectional hierarchy coverage:
train -> wagon, wagon -> feature, feature -> wmbt, wmbt -> acceptance.

Legacy parity note (honest): the legacy planner/tester hierarchy validators are
phase-gated *warn-only* (CURRENT_PHASE=1 < PLANNER_TESTER_ENFORCEMENT=2), so they
never fail regardless of fault. This variant is therefore CONVENTION-ONLY
(enforcing) — the fault-injection test below measures that directly rather than
claiming a parity it cannot reach.
"""
from __future__ import annotations

from atdd.validators.conventions.coverage import fixtures as F
from atdd.validators.conventions.coverage.archetype import (
    TEMPLATE_IDS,
    _hierarchy_coverage,
    _source_has_required_target,
)
from atdd.validators.conventions.coverage import _parity
from atdd.validators.conventions._support.graph_mutations import add_node, clone_graph

FAMILY = "coverage"
TEMPLATE = "source_has_required_target"
VARIANT = "hierarchy_coverage"
QUESTION = 'For every source node of type X, does required downstream target Y exist?'
SELECTOR = 'nodes where node.coverage.requires exists'
TRAVERSAL = 'source node -> required relationship/path -> target node set'
INVARIANT = 'target set is non-empty and satisfies required target kind/filter'
AUTO_CAPTURE = 'a new node is included if it declares coverage requirements'
FAILURE_EVIDENCE = ['source_node', 'required_target_kind', 'required_path', 'actual_targets']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_hierarchy_coverage.py', 'src/atdd/tester/validators/test_hierarchy_coverage.py']

def test_hierarchy_coverage_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in coverage archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    """Evaluating the variant on the real composed graph yields no violations."""
    root = _parity.repo_root()
    viols = _parity.conv_violations(root, _source_has_required_target,
                                    {"variant": VARIANT}, graph=clean_convention_graph)
    assert viols == [], f"clean baseline must be 0, got {viols[:3]}"


def test_fixture_valid_and_invalid() -> None:
    assert _hierarchy_coverage(F.valid_hierarchy()) == []
    inv = _hierarchy_coverage(F.invalid_hierarchy())
    kinds = {v["required_target_kind"] for v in inv}
    assert kinds == {"train", "feature", "wmbt", "acceptance"}, kinds
    for v in inv:  # evidence keys are a SUBSET of the template contract
        assert set(v).issubset(set(FAILURE_EVIDENCE)), set(v) - set(FAILURE_EVIDENCE)


_PROBE_WMBT = "wmbt:validate-conventions:E998"


def test_fault_injection_convention_catches(clean_convention_graph) -> None:
    """Inject a WMBT with no acceptances. The convention evaluator catches it.

    The WMBT node is added straight to a deep clone of the session graph (#1416) — the
    same node the on-disk ``E998.yaml`` used to add on rebuild — so the wmbt->acceptance
    hierarchy leg fires, with no plan/ file written and the shared graph untouched.

    Oracle retired (#1365): the legacy hierarchy validator (phase-gated warn-only,
    a convention-only improvement) is being decommissioned; the convention path is
    the live coverage."""
    faulted = clone_graph(clean_convention_graph)
    add_node(faulted, id=_PROBE_WMBT, kind="wmbt", fields={"urn": _PROBE_WMBT})

    conv = _source_has_required_target(faulted, {"variant": VARIANT})
    caught = [v for v in conv if v["source_node"] == _PROBE_WMBT]
    assert caught, "convention evaluator must catch the missing-acceptance WMBT"
    assert set(caught[0]).issubset(set(FAILURE_EVIDENCE))
    # the shared clean graph carried no such WMBT and stays clean
    assert _source_has_required_target(clean_convention_graph, {"variant": VARIANT}) == []
