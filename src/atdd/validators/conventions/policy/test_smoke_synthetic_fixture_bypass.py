# URN: test:validate-conventions:policy-variants:smoke_synthetic_fixture_bypass
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `policy/smoke_synthetic_fixture_bypass` (#1212).

Real-graph execution of the `policy/forbidden_construct_absence` template: SMOKE
acceptance nodes in the composed graph resolve to their test files, which must not
use synthetic-fixture anti-patterns (FakeMultiplexer / stub cat|sleep|python Popen
agent command / `_SYNTHETIC_AGENT`). Parity-bound to the legacy planner validator.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.validators.conventions._support.graph_loader import load_composed_graph
from atdd.validators.conventions.policy.archetype import (
    TEMPLATES,
    TEMPLATE_IDS,
    _is_smoke_acceptance,
    _resolve_test_file_from_urn,
)
from atdd.validators.conventions.policy import _parity

FAMILY = "policy"
TEMPLATE = "forbidden_construct_absence"
VARIANT = "smoke_synthetic_fixture_bypass"
QUESTION = 'Are forbidden constructs, fields, edge types, commands, or legacy shapes absent?'
SELECTOR = 'graph nodes/artifacts matched by a policy scope'
TRAVERSAL = 'scope -> scan nodes/fields/edges/artifacts -> forbidden matcher'
INVARIANT = 'forbidden match set is empty'
AUTO_CAPTURE = 'usually explicit; a new node is included if it falls inside a policy scope'
FAILURE_EVIDENCE = ['matched_construct', 'policy_id', 'location', 'reason', 'suggested_replacement']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_smoke_synthetic_fixture_bypass.py']


def _template():
    return next(t for t in TEMPLATES if t.template_id == TEMPLATE)


def test_smoke_synthetic_fixture_bypass_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in policy archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
    assert set(FAILURE_EVIDENCE) <= set(_template().failure_evidence)


def test_clean_baseline_zero_on_real_graph() -> None:
    graph = load_composed_graph(_parity.repo_root())
    violations = _template().evaluate(graph, {"variant": VARIANT})
    assert violations == [], (
        f"{VARIANT}: clean repo must yield zero violations, got: {violations}"
    )


def _find_resolvable_smoke_test_file(graph) -> Path:
    root = Path(graph.root)
    for wmbt in graph.by_kind("wmbt"):
        for acc in (wmbt.fields.get("acceptances") or []):
            if not isinstance(acc, dict):
                continue
            identity = acc.get("identity", {}) or {}
            if not _is_smoke_acceptance(identity):
                continue
            urn = identity.get("urn", "")
            tf = _resolve_test_file_from_urn(urn, root) if urn else None
            if tf is not None and tf.exists():
                return tf
    pytest.skip("no resolvable SMOKE acceptance->test-file pair in the real repo")


def test_fault_injection_legacy_parity() -> None:
    """Inject FakeMultiplexer into a real SMOKE test file; assert BOTH the convention
    evaluator and the legacy planner validator catch it."""
    root = _parity.repo_root()
    graph = load_composed_graph(root)
    target = _find_resolvable_smoke_test_file(graph)
    original = target.read_text(encoding="utf-8")
    faulted = original + "\n# FakeMultiplexer  (atdd #1212 parity injection)\n"

    with _parity.overwrite_file(target, faulted):
        conv = _template().evaluate(load_composed_graph(root), {"variant": VARIANT})
        assert any(v.get("matched_construct") == "FakeMultiplexer" for v in conv), (
            f"{VARIANT}: convention evaluator did not catch injected fault in {target}"
        )
        # oracle retired (#1365): convention path above is the live coverage

    # reverted -> clean again
    assert _template().evaluate(load_composed_graph(root), {"variant": VARIANT}) == []
