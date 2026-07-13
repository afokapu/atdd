# URN: test:isolate-provider-boundary:enforce-import-boundary:C001-UNIT-001-detects-core-importing-provider
# Acceptance: acc:isolate-provider-boundary:C001-UNIT-001-detects-core-importing-provider
# WMBT: wmbt:isolate-provider-boundary:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The static guard fails on a synthetic core module that imports a provider, shells out to gh, reads an issue number as code, consults the provider registry, or reaches a provider transitively through a core helper — naming the offending module and the forbidden import and citing the §8.1 boundary law — and it does NOT pass merely because the provider package is absent from the environment. Refs #1400.
"""A core module that reaches a provider is caught — from source, never by importing (C001-UNIT-001).

wagon: isolate-provider-boundary | feature: enforce-import-boundary | phase: RED
WMBT: wmbt:isolate-provider-boundary:C001

The last assertion is the one the whole check stands on. ``github`` is **not installed** in this
environment, and one of the synthetic modules raises ``RuntimeError`` the instant anything imports
it. A guard written the obvious way — ``try: import github / except ImportError: pass`` — would
report every one of these packages clean, and would report the *real* core clean for exactly the
same reason, on every CI runner core has ever had. It would be a check that can only pass.

So nothing here is imported. The guard reads source and parses it, and the module that explodes on
import is scanned exactly like the ones that do not.
"""
from __future__ import annotations

import importlib.util

from atdd.state import import_boundary

from ._seam import (
    EXPLODES_ON_IMPORT,
    HELPER_IMPORTS_PROVIDER,
    IMPORTS_A_HELPER,
    IMPORTS_PROVIDER,
    IMPORTS_REGISTRY,
    READS_ISSUE_NUMBER,
    SHELLS_OUT_TO_GH,
    core_package,
)


def test_c001_unit_001_detects_core_importing_provider(tmp_path) -> None:
    """Every way of reaching a provider from core is detected, named, and attributed to §8.1."""
    package = core_package(tmp_path, {
        "projection": IMPORTS_PROVIDER,
        "evidence": SHELLS_OUT_TO_GH,
        "ownership": READS_ISSUE_NUMBER,
        "policy": IMPORTS_REGISTRY,
        "trailers": IMPORTS_A_HELPER,
        "helper": HELPER_IMPORTS_PROVIDER,
        "secrets": EXPLODES_ON_IMPORT,
    })

    report = import_boundary.check(package)

    assert not report.ok, "a core module importing a provider must not pass the boundary guard"

    by_rule: dict = {}
    for violation in report.violations:
        by_rule.setdefault(violation.rule, []).append(violation)

    # The offending module AND the forbidden import are both named. A report that said only
    # "boundary violation" would leave the reader to go and find it.
    provider_deps = by_rule[import_boundary.RULE_PROVIDER_DEPENDENCY]
    offending_modules = {v.module.rsplit(".", 1)[-1] for v in provider_deps}
    assert offending_modules >= {"projection", "helper", "secrets"}
    assert {v.target for v in provider_deps} >= {"github", "requests"}

    # `trailers` imports no provider itself — it imports `helper`, which does. The walk is
    # transitive, so the dependency is reported where it actually lives.
    assert "helper" in offending_modules

    # The gh shell-out has no import to find; an import-only guard sails straight past it.
    assert any(v.module.endswith("evidence") for v in by_rule[import_boundary.RULE_GH_SHELL_OUT])

    # An issue number read as CODE — not as a key inside the provider's own external_refs subtree.
    assert any(v.target in {"issue_number", ".issue_number"}
               for v in by_rule[import_boundary.RULE_GITHUB_IDENTIFIER])

    # A lifecycle module that can consult the provider REGISTRY can make a decision that depends
    # on a provider, whatever it happens to do today (E001).
    assert any(v.target == "atdd.state.provider_seam"
               for v in by_rule[import_boundary.RULE_REGISTRY_CONSULTATION])

    rendered = report.render()
    assert import_boundary.BOUNDARY_LAW in rendered
    assert "§8.1" in rendered
    assert "projection" in rendered and "github" in rendered

    # The load-bearing claim. `github` is absent from this environment and `secrets.py` raises the
    # moment it is imported — and both were caught anyway, because the guard read the source and
    # executed none of it. A guard that imported what it inspects would have called this package
    # clean, and would call the real one clean for the very same reason.
    assert importlib.util.find_spec("github") is None, (
        "this acceptance is only meaningful while `github` is absent from the environment"
    )
    assert "secrets" in offending_modules, (
        "a module that raises on import must still be scanned — the guard reads source"
    )
