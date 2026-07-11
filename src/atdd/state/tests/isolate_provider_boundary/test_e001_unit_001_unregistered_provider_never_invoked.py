# URN: test:isolate-provider-boundary:register-sync-providers:E001-UNIT-001-unregistered-provider-never-invoked
# Acceptance: acc:isolate-provider-boundary:E001-UNIT-001-unregistered-provider-never-invoked
# WMBT: wmbt:isolate-provider-boundary:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: With zero providers registered the mirror path is a no-op returning an empty ExternalRefUpdate list; a lifecycle transition completes without ever reading the provider registry — proved by making the registry EXPLODE if consulted, and statically by the registry being unreachable from the lifecycle import closure; and a provider registered after the fact is still never invoked by lifecycle code. Refs #1400.
"""Lifecycle never asks. Not "does not today" — cannot (E001-UNIT-001).

wagon: isolate-provider-boundary | feature: register-sync-providers | phase: RED
WMBT: wmbt:isolate-provider-boundary:E001

"The lifecycle transition succeeds without reading the provider registry" is a negative, and a
negative asserted by watching a counter stay at zero is weak: it proves the registry was not read
*on this path, in this run*. So it is asserted twice, both times destructively.

At **runtime** the registry's entry point is replaced with one that raises. A lifecycle path that
consults it does not fail an assertion at the end of the test — it dies, at the line that asked.

**Statically**, the registry is not in the lifecycle import closure at all (C001), so no lifecycle
module can reach it whatever it does. Together those two say what the acceptance means: not that
lifecycle refrains from asking, but that it has nothing to ask.
"""
from __future__ import annotations

import pytest

from atdd.state import evidence, import_boundary, provider_seam

from ._seam import UID_X, StubProvider, document, factory, projection


def test_e001_unit_001_unregistered_provider_never_invoked() -> None:
    """Zero providers: the mirror is a no-op, and the lifecycle path never reaches the registry."""
    assert provider_seam.registered_names() == [], "core's resting state is zero providers"

    # The mirror path with nothing registered: a no-op returning an empty list of refs.
    documents = projection(document())
    result = provider_seam.mirror_all(provider_seam.discover_providers(), documents)

    assert result.updates == []
    assert result.alarms == []
    assert result.ok
    assert documents == projection(document()), "a no-op mirror writes nothing"


def test_e001_unit_001_lifecycle_transition_never_reads_the_registry(monkeypatch) -> None:
    """The registry is booby-trapped, and the lifecycle gate runs straight through it."""

    def explode() -> None:
        raise AssertionError(
            "a lifecycle decision consulted the provider registry — spec §8.1: core must run a "
            "complete workflow with zero providers registered"
        )

    monkeypatch.setattr(provider_seam, "discover_providers", explode)
    monkeypatch.setattr(provider_seam, "registered_names", explode)

    # The load-bearing lifecycle gate: is this phase transition legal, given its evidence (§6)?
    base = projection(document(phase="PLANNED"))
    head = projection(document(phase="RED"))
    report = evidence.validate_projection_diff(
        base, head,
        {UID_X: {"operator_token_digest", "gate_id", "failing_test_evidence"}},
    )

    # It reached a verdict, and it never asked what providers exist. Had it asked, the booby trap
    # would have fired inside the call above rather than failing an assertion down here.
    assert report.ok, report.render()


def test_e001_unit_001_a_provider_registered_after_the_fact_is_still_never_invoked(
    monkeypatch,
) -> None:
    """Registering a provider changes nothing about what lifecycle decides — it cannot see it."""
    spy = StubProvider(name="late")
    provider_seam.register_provider("late", factory(spy))
    assert provider_seam.registered_names() == ["late"]

    def explode() -> None:
        raise AssertionError("a lifecycle decision consulted the provider registry (spec §8.1)")

    monkeypatch.setattr(provider_seam, "discover_providers", explode)

    base = projection(document(phase="PLANNED"))
    head = projection(document(phase="RED"))
    report = evidence.validate_projection_diff(
        base, head,
        {UID_X: {"operator_token_digest", "gate_id", "failing_test_evidence"}},
    )

    assert report.ok, report.render()
    assert spy.seen == [], "the registered provider was never handed a snapshot by lifecycle code"


def test_e001_unit_001_the_registry_is_unreachable_from_lifecycle() -> None:
    """The static half: no lifecycle module can reach the registry, whatever it does at runtime."""
    report = import_boundary.check()

    assert report.ok, report.render()
    assert "atdd.state.provider_seam" not in report.scanned, (
        "the registry is reachable from a lifecycle module: a lifecycle decision COULD consult a "
        "provider, and 'it does not today' is not the property E001 asks for"
    )
