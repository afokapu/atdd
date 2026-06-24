# URN: test:validate-conventions:sizing-variants:wagon_coupling_complexity
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `sizing/wagon_coupling_complexity` (#1206).

Instantiates the `sizing/cardinality_bounds` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

import contextlib

import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.validators.conventions._support.graph_loader import load_composed_graph
from atdd.validators.conventions.sizing import _parity
from atdd.validators.conventions.sizing import fixtures as F
from atdd.validators.conventions.sizing.archetype import (
    TEMPLATE_IDS,
    TEMPLATES,
    evaluate_coupling_complexity,
)

FAMILY = "sizing"
TEMPLATE = "cardinality_bounds"
VARIANT = "wagon_coupling_complexity"
QUESTION = 'Is the number of related nodes within allowed min/max bounds?'
SELECTOR = 'nodes or scopes with declared cardinality constraints'
TRAVERSAL = 'source/scope -> collect related nodes -> count'
INVARIANT = 'min <= count <= max'
AUTO_CAPTURE = 'a new node is included if it declares cardinality constraints'
FAILURE_EVIDENCE = ['source_node_or_scope', 'relationship', 'actual_count', 'min', 'max', 'targets']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_wagon_coupling_complexity.py']


_CONFIG = {"variant": VARIANT}
_TEMPLATE = TEMPLATES[0]
_TARGET_WAGON = "freeze-runtime-contracts"
_TARGET_FILE = "plan/freeze_runtime_contracts/_freeze_runtime_contracts.yaml"
# 7 artifacts each PRODUCED by a distinct other wagon — consuming all of them gives
# the target fan_in=7; it already has fan_out=9, so complexity 63 >> threshold 6.
_INJECT_CONSUMES = [
    "commons:admit:substrate-schemas", "commons:author:plan-spine",
    "commons:bind:lock-loader", "commons:coach:pr-watcher-module",
    "commons:coach:concurrent-wave-driver", "commons:coach:canonical-coach-surface",
    "commons:author:substrate-schemas",
]


def _norm(slug: str) -> str:
    return slug.replace("_", "-")


def test_wagon_coupling_complexity_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in sizing archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_evidence_keys_subset_of_contract() -> None:
    """Every evidence dict's keys are a SUBSET of the template's failure_evidence."""
    allowed = set(FAILURE_EVIDENCE)
    findings = _TEMPLATE.evaluate(F.INVALID_FRAGMENTS[VARIANT], F.FIXTURE_CONFIG[VARIANT])
    assert findings
    for ev in findings:
        assert set(ev) <= allowed, f"evidence keys {set(ev)} escape contract {allowed}"


def test_fixture_fragments_valid_clean_invalid_flagged() -> None:
    """Real-graph fragments: VALID evaluates to [], INVALID to a non-empty finding."""
    cfg = F.FIXTURE_CONFIG[VARIANT]
    assert _TEMPLATE.evaluate(F.VALID_FRAGMENTS[VARIANT], cfg) == []
    assert _TEMPLATE.evaluate(F.INVALID_FRAGMENTS[VARIANT], cfg)


def test_clean_baseline_on_real_composed_graph() -> None:
    """On the live repo no wagon exceeds the soft coupling threshold (no false positives)."""
    graph = load_composed_graph(find_repo_root())
    assert _TEMPLATE.evaluate(graph, _CONFIG) == []
    assert evaluate_coupling_complexity(graph) == []


@contextlib.contextmanager
def _inject_consumes(root, rel, consumes):
    p = root / rel
    orig = p.read_text(encoding="utf-8")
    d = yaml.safe_load(orig)
    d["consume"] = [{"name": n, "contract": None, "telemetry": None, "from": "external"}
                    for n in consumes]
    p.write_text(yaml.safe_dump(d, sort_keys=False), encoding="utf-8")
    try:
        yield
    finally:
        p.write_text(orig, encoding="utf-8")


def test_fault_injection_legacy_parity() -> None:
    """Inject an over-coupling fault into a real wagon manifest; assert BOTH the
    convention evaluator AND the legacy validator flag the same wagon, then revert.

    The legacy validator's ADVISORY pytest test (assert_disposition_satisfied) PASSES
    even with findings, so a subprocess return code is NOT a parity signal here; we run
    the legacy SCAN function in-process on the identical faulted tree — the direct,
    honest measurement of whether legacy catches the same fault.
    """
    root = find_repo_root()
    with _inject_consumes(root, _TARGET_FILE, _INJECT_CONSUMES):
        graph = load_composed_graph(root)
        conv = {_norm(ev["source_node_or_scope"].split(":", 1)[1])
                for ev in evaluate_coupling_complexity(graph)}
        leg = {_norm(v.location.split("/")[1])
               for v in _parity.legacy_coupling_scan(root)}

    assert _TARGET_WAGON in conv, f"convention missed injected fault: {conv}"
    assert _TARGET_WAGON in leg, f"legacy missed injected fault: {leg}"
    assert _TARGET_WAGON in (conv & leg), "PARITY: both must catch the same wagon"
