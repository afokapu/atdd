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

from atdd.validators.conventions._support.graph_mutations import (
    graph_rooted_at,
    stage_file,
)
from atdd.validators.conventions.policy.archetype import TEMPLATES, TEMPLATE_IDS

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


_PROBE_REL = "src/atdd/_stale_suppression_probe.py"


def test_fault_injection(clean_convention_graph, tmp_path) -> None:
    """Stage a file carrying a past-deadline suppression marker under a temp root;
    assert the convention evaluator catches it, and that the real tree is untouched.

    Legacy parity (verdict `both`) was proven against
    test_no_stale_suppressions.py::test_no_stale_suppressions before that legacy
    validator was decommissioned (#1207); coach.rule-id.stale-suppression now binds
    its implementation.ref to this variant. The convention fault-injection is the
    live coverage.

    The scanner is a pure filesystem scanner — it takes the graph only to read
    `.root` and then rglobs `_STALE_SCAN_ROOTS` — so the fault has to be a real file
    it really reads, and there is no node to mutate. It does NOT have to be a real
    file in the REAL checkout (#1458, E035): the probe is staged under `tmp_path` at
    the same relative path and the graph is re-pointed there. Same scanner, same code
    path — it just walks a two-file tree instead of the whole repo, so the two graph
    rebuilds AND the `src/atdd/*.py` residue both go away.
    """
    # Build the pragma at runtime so no contiguous `atdd:suppress(...)` literal
    # appears in this committed test file (which the scanner itself walks).
    pragma = "atdd:" + "suppress(demo.parity.rule)" + " UNTIL=2000-01-01"
    stage_file(tmp_path, _PROBE_REL, f"x = 1  # {pragma}\n")

    staged = graph_rooted_at(clean_convention_graph, tmp_path)
    conv = _template().evaluate(staged, {"variant": VARIANT})

    hit = [v for v in conv if v.get("location", "").endswith("_stale_suppression_probe.py:1")]
    assert hit, f"{VARIANT}: convention evaluator did not catch injected stale marker"
    assert "UNTIL=2000-01-01" in hit[0]["matched_construct"]

    # The real checkout carries no stale marker and was never written to.
    assert _template().evaluate(clean_convention_graph, {"variant": VARIANT}) == []
