# URN: test:validate-conventions:coverage-variants:no_orphan_nodes
# Acceptance: acc:author-atdd-substrate:C008-SMOKE-001-no-orphan-nodes
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `coverage/no_orphan_nodes` (#1206 / #1212).

Instantiates the `coverage/reachability_no_orphan` template against the composed convention
graph. Every rule-bearing convention node (a `*.convention.yaml` with a top-level
`rule_id`; fixtures and the `demo.*` namespace excluded) must be reachable as a
`source_ref`/`target_ref` endpoint of the relationship graph
(`src/atdd/coach/graph/relationships.yaml`). The evaluator reads the same two real
sources legacy reads, via `graph.root`.

Legacy parity: proven and recorded (#1212). The fault-injection test below injects an
orphan convention node and proves the convention evaluator flags it; the legacy oracle
leg was dropped when the legacy validator was retired (#1207 sweep, #1385).
"""
from __future__ import annotations

from atdd.validators.conventions.coverage.archetype import (
    TEMPLATE_IDS,
    _reachability_no_orphan,
)
from atdd.validators.conventions.coverage import _parity

FAMILY = "coverage"
TEMPLATE = "reachability_no_orphan"
VARIANT = "no_orphan_nodes"
QUESTION = 'Is every required node reachable from a valid root or owner?'
SELECTOR = 'nodes where requires_reachability != false'
TRAVERSAL = 'root nodes -> allowed edges -> reachable set'
INVARIANT = 'eligible node is in reachable set'
AUTO_CAPTURE = 'a new node is included if its kind/package requires reachability by default'
FAILURE_EVIDENCE = ['orphan_node', 'expected_root', 'allowed_paths', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_no_orphan_nodes.py']

def test_no_orphan_nodes_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in coverage archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    """Real repo: every rule-bearing convention node is a relationship endpoint."""
    root = _parity.repo_root()
    viols = _parity.conv_violations(root, _reachability_no_orphan,
                                    graph=clean_convention_graph)
    assert viols == [], f"clean baseline must be 0, got {viols[:3]}"


def test_fault_injection_legacy_parity_both_catch() -> None:
    """Inject a convention node whose rule_id appears on no relationship edge; the
    convention evaluator must catch it on the faulted tree and stay clean once
    reverted."""
    root = _parity.repo_root()
    rel = "src/atdd/planner/conventions/nodes/_tmp_coverage_orphan_probe.convention.yaml"
    content = (
        "rule_id: planner.tmp.coverage-orphan-probe-xyz\n"
        'version: "1.0"\n'
        'description: "temp orphan probe (#1212 parity test)"\n'
    )

    with _parity.inject_tempfile(root, rel, content):
        conv = _parity.conv_violations(root, _reachability_no_orphan)
    caught = [v for v in conv
              if v["orphan_node"] == "planner.tmp.coverage-orphan-probe-xyz"]
    assert caught, "convention evaluator must catch the orphan convention node"
    assert set(caught[0]).issubset(set(FAILURE_EVIDENCE))
    # oracle retired (#1385): convention path above is the live coverage
    assert _parity.conv_violations(root, _reachability_no_orphan) == []
