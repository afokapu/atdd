# URN: test:bind-extension-conventions:bind-extension-conventions:E001-SMOKE-001-live-fanout-binds-all-gating-rules
# Acceptance: acc:bind-extension-conventions:E001-SMOKE-001-live-fanout-binds-all-gating-rules
# WMBT: wmbt:bind-extension-conventions:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:bind-extension-conventions:E001-SMOKE-001-live-fanout-binds-all-gating-rules.

Composing the binding plan from the toolkit's own real ``.atdd/workspaces``
implementation manifests (now declaring ``realizes_convention`` as ownership
lists) binds every one of the 26 fanned-out gating conventions and reaches 52
bound entries — with no new implementation shipped.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.substrate.binding.plan import build_binding_plan

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


def test_live_fanout_binds_all_gating_rules() -> None:
    repo_root = find_repo_root()

    plan = build_binding_plan(repo_root)
    bound = {
        c["convention_id"]
        for c in plan["conventions"]
        if c.get("disposition") == "bound"
    }

    # Every one of the 26 previously-unbound gating conventions is now bound.
    missing = _EXPECTED_GATING_UNBOUND - bound
    assert not missing, f"fan-out failed to bind: {sorted(missing)}"

    # The plan binds exactly 52 conventions (26 detectors' owned rules).
    assert len(bound) == 52, f"expected 52 bound, got {len(bound)}"
