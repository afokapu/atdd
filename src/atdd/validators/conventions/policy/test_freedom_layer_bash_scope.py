# URN: test:validate-conventions:policy-variants:freedom_layer_bash_scope
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `policy/freedom_layer_bash_scope` (#1212, E032).

Real-graph execution of the `policy/forbidden_construct_absence` template: reads the
real `session.convention.yaml::spawn_time.freedom_layer` and forbids any
`allowed_bash` entry that is not tightly scoped `Bash(<cmd>:*)` or that
pre-authorizes a `forbidden_bash` command. Parity-bound to the legacy coach E032
freedom-layer validator (live SMOKE).
"""
from __future__ import annotations

import yaml

from atdd.validators.conventions._support.graph_loader import load_composed_graph
from atdd.validators.conventions.policy.archetype import (
    TEMPLATES,
    TEMPLATE_IDS,
    _SESSION_CONVENTION,
)
from atdd.validators.conventions.policy import _parity

FAMILY = "policy"
TEMPLATE = "forbidden_construct_absence"
VARIANT = "freedom_layer_bash_scope"
QUESTION = 'Are forbidden constructs, fields, edge types, commands, or legacy shapes absent?'
SELECTOR = 'graph nodes/artifacts matched by a policy scope'
TRAVERSAL = 'scope -> scan nodes/fields/edges/artifacts -> forbidden matcher'
INVARIANT = 'forbidden match set is empty'
AUTO_CAPTURE = 'usually explicit; a new node is included if it falls inside a policy scope'
FAILURE_EVIDENCE = ['matched_construct', 'policy_id', 'location', 'reason', 'suggested_replacement']
LEGACY_PARITY_SOURCES = [
    'src/atdd/coach/validators/test_e032_smoke_001_live_freedom_layer_passes_flipped_validator.py'
]
# Legacy parity oracle RETIRED (#1207): the legacy E032 validator was deleted once
# `both`-parity was proven (family-parity-report: policy = 4/4 both, grammar live-smoke
# counterpart). LEGACY_PARITY_SOURCES kept as the provenance record.


def _template():
    return next(t for t in TEMPLATES if t.template_id == TEMPLATE)


def test_freedom_layer_bash_scope_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in policy archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE) <= set(_template().failure_evidence)


def test_clean_baseline_zero_on_real_graph() -> None:
    graph = load_composed_graph(_parity.repo_root())
    violations = _template().evaluate(graph, {"variant": VARIANT})
    assert violations == [], (
        f"{VARIANT}: clean repo must yield zero violations, got: {violations}"
    )


def test_fault_injection() -> None:
    """Pre-authorize a forbidden command in the real freedom_layer allow-list; assert
    the convention evaluator catches it (legacy oracle retired, #1207)."""
    root = _parity.repo_root()
    conv_path = root / _SESSION_CONVENTION
    data = yaml.safe_load(conv_path.read_text(encoding="utf-8"))
    data["spawn_time"]["freedom_layer"]["allowed_bash"].append("Bash(git push:*)")
    faulted = yaml.safe_dump(data, sort_keys=False)

    with _parity.overwrite_file(conv_path, faulted):
        conv = _template().evaluate(load_composed_graph(root), {"variant": VARIANT})
        assert any("git push" in v.get("matched_construct", "") for v in conv), (
            f"{VARIANT}: convention evaluator did not catch the forbidden allowed_bash entry"
        )

    assert _template().evaluate(load_composed_graph(root), {"variant": VARIANT}) == []
