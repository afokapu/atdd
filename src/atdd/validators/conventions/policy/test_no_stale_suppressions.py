# URN: test:validate-conventions:policy-variants:no_stale_suppressions
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `policy/no_stale_suppressions` (#1212).

Real-graph execution of the `policy/forbidden_construct_absence` template: scans the
real suppression-marker corpus under the repo (graph.root) for any
`# atdd:suppress(<id>) UNTIL=<date>` marker whose deadline is past. Parity-bound to
the legacy coach validator.
"""
from __future__ import annotations

import pytest

from atdd.validators.conventions._support.graph_loader import load_composed_graph
from atdd.validators.conventions.policy.archetype import TEMPLATES, TEMPLATE_IDS
from atdd.validators.conventions.policy import _parity

FAMILY = "policy"
TEMPLATE = "forbidden_construct_absence"
VARIANT = "no_stale_suppressions"
QUESTION = 'Are forbidden constructs, fields, edge types, commands, or legacy shapes absent?'
SELECTOR = 'graph nodes/artifacts matched by a policy scope'
TRAVERSAL = 'scope -> scan nodes/fields/edges/artifacts -> forbidden matcher'
INVARIANT = 'forbidden match set is empty'
AUTO_CAPTURE = 'usually explicit; a new node is included if it falls inside a policy scope'
FAILURE_EVIDENCE = ['matched_construct', 'policy_id', 'location', 'reason', 'suggested_replacement']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_no_stale_suppressions.py']


def _template():
    return next(t for t in TEMPLATES if t.template_id == TEMPLATE)


def test_no_stale_suppressions_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in policy archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE) <= set(_template().failure_evidence)


def test_clean_baseline_zero_on_real_graph(clean_convention_graph) -> None:
    violations = _template().evaluate(clean_convention_graph, {"variant": VARIANT})
    assert violations == [], (
        f"{VARIANT}: clean repo must yield zero violations, got: {violations}"
    )


@pytest.mark.convention_filesystem_mutation
def test_fault_injection() -> None:
    """Create a real file under src/atdd carrying a past-deadline suppression marker;
    assert the convention evaluator catches it, then confirm clean after revert.

    Legacy parity (verdict `both`) was proven against
    test_no_stale_suppressions.py::test_no_stale_suppressions before that legacy
    validator was decommissioned (#1207); coach.rule-id.stale-suppression now binds
    its implementation.ref to this variant. The convention fault-injection is the
    live coverage."""
    root = _parity.repo_root()
    inj = root / "src" / "atdd" / "_atdd1212_stale_suppression_parity.py"
    # Build the pragma at runtime so no contiguous `atdd:suppress(...)` literal
    # appears in this committed test file (which the scanner itself walks).
    pragma = "atdd:" + "suppress(demo.parity.rule)" + " UNTIL=2000-01-01"
    marker = f"x = 1  # {pragma}\n"

    with _parity.temp_new_file(inj, marker):
        conv = _template().evaluate(load_composed_graph(root), {"variant": VARIANT})
        hit = [v for v in conv if v.get("location", "").endswith(f"{inj.name}:1")]
        assert hit, f"{VARIANT}: convention evaluator did not catch injected stale marker"
        assert "UNTIL=2000-01-01" in hit[0]["matched_construct"]

    assert _template().evaluate(load_composed_graph(root), {"variant": VARIANT}) == []
