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

from atdd.validators.conventions._support.graph_mutations import (
    graph_rooted_at,
    mirror_file,
)
from atdd.validators.conventions.policy.archetype import (
    TEMPLATES,
    TEMPLATE_IDS,
    _is_smoke_acceptance,
    _resolve_test_file_from_urn,
)

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


def test_clean_baseline_zero_on_real_graph(clean_convention_graph) -> None:
    violations = _template().evaluate(clean_convention_graph, {"variant": VARIANT})
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


def test_fault_injection_legacy_parity(clean_convention_graph, tmp_path) -> None:
    """Inject FakeMultiplexer into a STAGED COPY of a real SMOKE test file; assert the
    convention evaluator catches it and that the committed test file is untouched.

    The scanner selects its targets from the graph's real WMBT nodes but reads the
    FAULT out of the resolved test file's source text, so the fault has to be a real
    `.py` the scanner really reads — no node carries it. Previously that meant
    overwriting a committed SMOKE test in the working tree and restoring it in a
    `finally`; a crash mid-test left a corrupted test file behind (#1458, E035).

    Instead the real target is resolved against the real root, mirrored into `tmp_path`
    at its own relative path with the fault appended, and the graph re-pointed there.
    The evaluator still walks the real WMBT acceptance nodes — they are shared with the
    session graph, and the fault does not touch them — resolves the same URN to the
    mirrored copy, and flags it.
    """
    root = clean_convention_graph.root
    target = _find_resolvable_smoke_test_file(clean_convention_graph)
    rel = str(Path(target).relative_to(root))

    mirror_file(
        root, tmp_path, rel,
        lambda t: t + "\n# FakeMultiplexer  (atdd #1212 parity injection)\n",
    )

    staged = graph_rooted_at(clean_convention_graph, tmp_path)
    conv = _template().evaluate(staged, {"variant": VARIANT})
    assert any(v.get("matched_construct") == "FakeMultiplexer" for v in conv), (
        f"{VARIANT}: convention evaluator did not catch injected fault in {rel}"
    )
    # oracle retired (#1365): convention path above is the live coverage

    # The committed SMOKE tests carry no synthetic fixture and were never written to.
    assert _template().evaluate(clean_convention_graph, {"variant": VARIANT}) == []
