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

import pytest

from atdd.validators.conventions.coverage.archetype import (
    TEMPLATE_IDS,
    _reachability_no_orphan,
)
from atdd.validators.conventions.coverage import _parity
from atdd.validators.conventions._support.graph_mutations import (
    graph_rooted_at,
    mirror_file,
    mirror_glob,
    stage_file,
)

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


def test_fault_injection_legacy_parity_both_catch(clean_convention_graph, tmp_path) -> None:
    """A convention node whose rule_id appears on no relationship edge is caught — and
    nothing else is.

    This evaluator reads no node: it GLOBS every ``*.convention.yaml`` under ``src/atdd``
    and reads ``relationships.yaml``, both through ``graph.root``. So the fault must be a
    real file — but the tree it lives in need not be the checkout (#1458).

    The staged tree mirrors the evaluator's ENTIRE real input surface (every convention
    file, plus the relationship graph) and drops the orphan probe into it. Staging the
    probe ALONE would have been cheaper and wrong: against a tree containing nothing but
    the fault, the evaluator would flag it no matter how broken its reachability logic
    was, and could not show that a legitimate node stays unflagged. Mirroring the real
    surface buys the strong assertion instead — the probe is flagged and the ~367 real
    convention nodes are not, which is the clean baseline and the fault in ONE run.
    """
    root = _parity.repo_root()
    mirror_glob(root, tmp_path, "src/atdd", "*.convention.yaml")
    mirror_file(root, tmp_path, "src/atdd/coach/graph/relationships.yaml")
    stage_file(
        tmp_path,
        "src/atdd/planner/conventions/nodes/_tmp_coverage_orphan_probe.convention.yaml",
        "rule_id: planner.tmp.coverage-orphan-probe-xyz\n"
        'version: "1.0"\n'
        'description: "orphan probe (#1212 parity test)"\n',
    )

    conv = _reachability_no_orphan(graph_rooted_at(clean_convention_graph, tmp_path))

    # oracle retired (#1385): the convention path is the live coverage.
    assert [v["orphan_node"] for v in conv] == ["planner.tmp.coverage-orphan-probe-xyz"], (
        f"the orphan probe must be the ONLY node flagged on the mirrored surface: {conv}"
    )
    assert set(conv[0]).issubset(set(FAILURE_EVIDENCE))
