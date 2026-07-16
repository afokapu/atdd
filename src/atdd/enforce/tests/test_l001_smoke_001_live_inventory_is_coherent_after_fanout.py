# URN: test:bind-extension-conventions:bind-extension-conventions:L001-SMOKE-001-live-inventory-is-coherent-after-fanout
# Acceptance: acc:bind-extension-conventions:L001-SMOKE-001-live-inventory-is-coherent-after-fanout
# WMBT: wmbt:bind-extension-conventions:L001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:bind-extension-conventions:L001-SMOKE-001-live-inventory-is-coherent-after-fanout.

Over the toolkit's own real committed ``.atdd/extensions`` convention nodes and
regenerated ``.atdd/binding.lock.yaml``, the live binding-gap inventory is
coherent: no gating obligation is unbound, the only declared-not-bound nodes are
the two documentation-only exemptions, and the four core-declared ``tester.*``
phantoms remain the only bound-not-declared entries. The same inventory,
recomputed against the pre-fan-out bound set, reproduces the diagnosed gap
(28 declared-not-bound, 22 overlap, 26 gating obligations, 4 phantoms) — the
gap the fan-out closed.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.binding_gap import compute_binding_gap, live_binding_gap, load_declared_extension_nodes
from atdd.enforce.runner import resolve_substrate_home

_DOC_ONLY_EXEMPT = {
    "coder.performance.perf",
    "tester.migration.naming",
}

# The four bound tester.* detectors whose convention node lives in core rather
# than under .atdd/extensions — phantom relative to the extension node set.
_KNOWN_PHANTOMS = {
    "tester.acceptance-violation.live-smoke-acceptance-must-execute",
    "tester.acceptance-violation.metric-implementation-must-exist",
    "tester.smoke.no-collaborator-substitution",
    "tester.test-isolation.no-polluting-patterns",
}

# The 26 gating obligations the 11 multi-rule detectors emit but that were
# unbound before the implementation fan-out.
_EXPECTED_GATING_UNBOUND = {
    "coder.boundaries.xlang-contract",
    "coder.boundaries.xlang-enum",
    "coder.boundaries.xlang-naming",
    "coder.design.foundations",
    "coder.design.hierarchy-import",
    "coder.design.orphan-export",
    "coder.design.orphan-ui",
    "coder.design.token-color",
    "coder.design.token-hardcoded",
    "coder.error-response.code-format",
    "coder.presentation.gsap-commons",
    "coder.presentation.i18n-switcher",
    "coder.refactor.complexity-cognitive",
    "coder.refactor.complexity-length",
    "coder.refactor.complexity-length-typescript",
    "coder.refactor.complexity-nesting",
    "coder.refactor.complexity-nesting-typescript",
    "coder.refactor.complexity-params",
    "coder.refactor.composition-root",
    "coder.refactor.quality-comments",
    "coder.refactor.quality-comments-typescript",
    "coder.refactor.quality-duplication",
    "coder.refactor.quality-file-length",
    "coder.refactor.quality-naming",
    "coder.security.hardcoded-secret",
    "coder.security.missing-auth",
}

# The 26 conventions bound before the fan-out (scalar realizes_convention).
_PRE_FANOUT_BOUND = {
    "coder.boundaries.http-client",
    "coder.boundaries.xlang-entity",
    "coder.dead-code.reachability",
    "coder.dead-code.reachability-typescript",
    "coder.design.primitives",
    "coder.duplication.no-intra-layer-code-python",
    "coder.duplication.no-intra-layer-code-typescript",
    "coder.error-response.bare-string",
    "coder.logging.coach-silent-swallow",
    "coder.logging.print",
    "coder.logging.structured",
    "coder.presentation.gsap-layer",
    "coder.presentation.i18n-config",
    "coder.refactor.coach-ratchet-pres",
    "coder.refactor.complexity-cyclomatic",
    "coder.refactor.complexity-cyclomatic-typescript",
    "coder.refactor.composition-consumer",
    "coder.refactor.nplus1",
    "coder.refactor.quality-mi",
    "coder.refactor.quality-mi-typescript",
    "coder.security.sql-injection",
    "tester.acceptance-violation.live-smoke-acceptance-must-execute",
    "tester.acceptance-violation.metric-implementation-must-exist",
    "tester.filename.urn",
    "tester.smoke.no-collaborator-substitution",
    "tester.test-isolation.no-polluting-patterns",
}


def test_live_inventory_is_coherent_after_fanout() -> None:
    substrate_home = resolve_substrate_home(find_repo_root())

    live = live_binding_gap(substrate_home)

    # Every gating obligation is now bound.
    assert live.gating_unbound == frozenset(), (
        f"gating obligations still unbound after fan-out: {sorted(live.gating_unbound)}"
    )
    # The only declared-not-bound nodes are the documentation-only exemptions.
    assert live.doc_only_unbound == _DOC_ONLY_EXEMPT
    assert live.declared_not_bound == _DOC_ONLY_EXEMPT
    # The four core-declared tester phantoms are the only bound-not-declared entries.
    assert live.bound_not_declared == _KNOWN_PHANTOMS
    # The split of declared-not-bound is exhaustive.
    assert live.gating_unbound | live.doc_only_unbound == live.declared_not_bound

    # The same inventory, recomputed over the pre-fan-out bound set, names the
    # gap the fan-out closed: 22 overlap, 28 declared-not-bound (26 gating + 2
    # doc-only), 4 phantoms.
    declared = load_declared_extension_nodes(substrate_home)
    assert len(declared) == 50
    pre = compute_binding_gap(declared, _PRE_FANOUT_BOUND)
    assert len(pre.overlap) == 22
    assert len(pre.declared_not_bound) == 28
    assert pre.gating_unbound == _EXPECTED_GATING_UNBOUND
    assert pre.doc_only_unbound == _DOC_ONLY_EXEMPT
    assert pre.bound_not_declared == _KNOWN_PHANTOMS
