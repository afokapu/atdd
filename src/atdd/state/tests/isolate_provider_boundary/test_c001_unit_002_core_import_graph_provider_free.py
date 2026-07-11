# URN: test:isolate-provider-boundary:enforce-import-boundary:C001-UNIT-002-core-import-graph-provider-free
# Acceptance: acc:isolate-provider-boundary:C001-UNIT-002-core-import-graph-provider-free
# WMBT: wmbt:isolate-provider-boundary:C001
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The REAL core import graph, walked transitively from every lifecycle module, carries no provider, gh, GitHub-API, or provider-registry import and no GitHub concept read as code — and the walk is deterministic and needs no network. Refs #1400.
"""The core this repository actually ships is provider-free (C001-UNIT-002).

wagon: isolate-provider-boundary | feature: enforce-import-boundary | phase: GREEN
WMBT: wmbt:isolate-provider-boundary:C001

Not a synthetic package: **this** one, as checked out. The walk starts at every lifecycle module
and follows first-party imports as far as they go, so the claim is about the transitive closure —
a lifecycle module that imported a core helper that imported ``github`` would fail here even
though it typed no forbidden import itself.

The second half of the acceptance is the registry. ``atdd.state.provider_seam`` is core, and core
may of course contain it — but nothing *reachable from a lifecycle decision* may import it, or a
lifecycle decision could consult a provider. That the registry is absent from a 27-module closure
is not an accident of today's imports; it is the property E001 depends on.
"""
from __future__ import annotations

from atdd.state import import_boundary


def test_c001_unit_002_core_import_graph_provider_free() -> None:
    """The real graph reaches no provider, no gh, no GitHub API, and no provider registry."""
    report = import_boundary.check()

    assert report.ok, report.render()
    assert not report.violations

    # The walk actually walked: every lifecycle module was a root, and the closure is bigger than
    # the roots (so first-party imports were followed, not merely listed).
    assert len(report.roots) == len(import_boundary.LIFECYCLE_MODULES)
    assert len(report.scanned) > len(report.roots)
    assert "atdd.state.merge_authority" in report.scanned
    assert "atdd.state.store" in report.scanned, "the walk follows imports into the store layer"

    # No lifecycle decision can reach the provider registry. This is what lets E001 say the
    # registry is never consulted — not a convention, an unreachability.
    for registry in import_boundary.REGISTRY_MODULES:
        assert registry not in report.scanned, (
            f"{registry} is reachable from a lifecycle module: a lifecycle decision could consult "
            f"a provider. {import_boundary.BOUNDARY_LAW}"
        )

    # Deterministic and offline: same verdict twice, and the guard imports nothing to reach it.
    again = import_boundary.check()
    assert again.scanned == report.scanned
    assert again.violations == report.violations
    assert report.render() == again.render()
