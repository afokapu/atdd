# URN: test:validate-conventions:policy-variants:bypass_inventory
# Acceptance: acc:govern-lifecycle:E026-UNIT-005-meta-guard-fails-when-bypass-count-grows
# Acceptance: acc:govern-lifecycle:E030-UNIT-003-meta-guard-baseline-is-zero
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

from atdd.validators.conventions._support.graph_mutations import (
    graph_rooted_at,
    mirror_file,
)
from atdd.validators.conventions.policy.archetype import (
    TEMPLATES,
    TEMPLATE_IDS,
    _HOOK_DIR,
    _HOOK_FILES,
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


def test_clean_baseline_zero_on_real_graph(clean_convention_graph) -> None:
    violations = _template().evaluate(clean_convention_graph, {"variant": VARIANT})
    assert violations == [], (
        f"{VARIANT}: clean repo must yield zero violations, got: {violations}"
    )


_BYPASS_LINE = '\nif [ "${ATDD_SKIP_PARITY_1212:-0}" = "1" ]; then exit 0; fi\n'


def test_fault_injection_legacy_parity(clean_convention_graph, tmp_path) -> None:
    """Reintroduce an ATDD_SKIP_* bypass flag into a staged copy of the real pre-push
    hook; assert the convention evaluator catches it and the real hook is untouched.

    The scanner reads the hook FILES under `graph.root` — there is no hook node to
    mutate, so the fault must be a real file it really parses. It need not be the real
    checkout's file (#1458, E035): every hook is mirrored into `tmp_path` from its own
    bytes at its own relative path, pre-push is faulted in the copy, and the graph is
    re-pointed at the temp tree. The evaluator runs the identical scan over identical
    bytes — but the repo's git hooks are never rewritten mid-test, which is worth more
    than the two graph builds this also saves.

    Oracle retired (#1365): the convention path below is the live coverage.
    """
    root = _parity.repo_root()
    for name in _HOOK_FILES:
        if not (root / _HOOK_DIR / name).is_file():
            continue
        rel = f"{_HOOK_DIR}/{name}"
        fault = (lambda t: t + _BYPASS_LINE) if name == "pre-push" else None
        mirror_file(root, tmp_path, rel, fault)

    staged = graph_rooted_at(clean_convention_graph, tmp_path)
    conv = _template().evaluate(staged, {"variant": VARIANT})
    assert any(v.get("matched_construct") == "ATDD_SKIP_PARITY_1212" for v in conv), (
        f"{VARIANT}: convention evaluator did not catch injected bypass flag"
    )

    # The real hooks carry no bypass flag and were never written to.
    assert _template().evaluate(clean_convention_graph, {"variant": VARIANT}) == []
