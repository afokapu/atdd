# URN: test:validate-conventions:policy-variants:bypass_inventory
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `policy/bypass_inventory` (#1212, E026).

Real-graph execution of the `policy/forbidden_construct_absence` template: scans the
real git-hook source files for any `ATDD_SKIP_*` enforcement-bypass flag (audited
baseline = 0; advisory `ATDD_MAX_*` and CI-only `ATDD_ALLOW_MAIN_*` excluded).
Parity-bound to the legacy coach E026 bypass-inventory guard.
"""
from __future__ import annotations

from atdd.validators.conventions._support.graph_loader import load_composed_graph
from atdd.validators.conventions.policy.archetype import (
    TEMPLATES,
    TEMPLATE_IDS,
    _HOOK_DIR,
)
from atdd.validators.conventions.policy import _parity

FAMILY = "policy"
TEMPLATE = "forbidden_construct_absence"
VARIANT = "bypass_inventory"
QUESTION = 'Are forbidden constructs, fields, edge types, commands, or legacy shapes absent?'
SELECTOR = 'graph nodes/artifacts matched by a policy scope'
TRAVERSAL = 'scope -> scan nodes/fields/edges/artifacts -> forbidden matcher'
INVARIANT = 'forbidden match set is empty'
AUTO_CAPTURE = 'usually explicit; a new node is included if it falls inside a policy scope'
FAILURE_EVIDENCE = ['matched_construct', 'policy_id', 'location', 'reason', 'suggested_replacement']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_e026_bypass_inventory_guard.py']


def _template():
    return next(t for t in TEMPLATES if t.template_id == TEMPLATE)


def test_bypass_inventory_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in policy archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE) <= set(_template().failure_evidence)


def test_clean_baseline_zero_on_real_graph() -> None:
    graph = load_composed_graph(_parity.repo_root())
    violations = _template().evaluate(graph, {"variant": VARIANT})
    assert violations == [], (
        f"{VARIANT}: clean repo must yield zero violations, got: {violations}"
    )


def test_fault_injection_convention_catches() -> None:
    """Reintroduce an ATDD_SKIP_* bypass flag into the real pre-push hook; assert the
    convention evaluator catches it.

    Legacy parity oracle retired (#1207): parity to the E026 guard was already
    proven/recorded (family-parity-report); the legacy anchored test is
    decommissioned. LEGACY_PARITY_SOURCES kept as provenance; this variant's own
    clean-baseline + fault-injection are the live coverage."""
    root = _parity.repo_root()
    hook = root / _HOOK_DIR / "pre-push"
    faulted = hook.read_text(encoding="utf-8") + (
        '\nif [ "${ATDD_SKIP_PARITY_1212:-0}" = "1" ]; then exit 0; fi\n'
    )

    with _parity.overwrite_file(hook, faulted):
        conv = _template().evaluate(load_composed_graph(root), {"variant": VARIANT})
        assert any(v.get("matched_construct") == "ATDD_SKIP_PARITY_1212" for v in conv), (
            f"{VARIANT}: convention evaluator did not catch injected bypass flag"
        )

    assert _template().evaluate(load_composed_graph(root), {"variant": VARIANT}) == []
