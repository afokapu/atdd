# URN: test:isolate-provider-boundary:verify-remote-conformance:C002-INTEGRATION-001-fails-when-lifecycle-reads-provider
# Acceptance: acc:isolate-provider-boundary:C002-INTEGRATION-001-fails-when-lifecycle-reads-provider
# WMBT: wmbt:isolate-provider-boundary:C002
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: When a lifecycle step is instrumented to consult the provider registry, read external_refs, or shell out to gh, the bare-remote conformance suite FAILS — naming the offending step and attributing the failure to invariant I7 — even though the step itself succeeded and every other step passed. Refs #1400.
"""The suite fails on a step that touches a provider, even when the step "works" (C002-INTEGRATION-001).

wagon: isolate-provider-boundary | feature: verify-remote-conformance | phase: RED
WMBT: wmbt:isolate-provider-boundary:C002

This is the acceptance that gives the GREEN one its meaning. A conformance suite that has never
been seen to fail is a suite nobody knows the shape of — it might be asserting the workflow is
provider-free, or it might be asserting nothing at all, and from the outside those look identical.

So three rogue steps are substituted in, one per tripwire, and each of them **succeeds**: it does
its work, returns a report line, and passes. The suite fails anyway, because succeeding is not the
question. The question is what the step had to touch to succeed, and the answer is recorded and
named and attributed to I7 — *the mirror is non-authoritative* — which is the invariant a lifecycle
step breaks when it makes its decision depend on a picture of the decision.
"""
from __future__ import annotations

from atdd.state import conformance, provider_seam
from atdd.state.conformance import Context, Step


def _rogue_registry(context: Context) -> str:
    """A 'lifecycle' step that asks what providers exist. It works. That is the problem."""
    providers = provider_seam.discover_providers()
    return f"consulted the registry and found {len(providers)} provider(s)"


def _rogue_external_refs(context: Context) -> str:
    """A 'lifecycle' step that reads the mirror's subtree to make its decision (§8.2 rule 5).

    It reads with ``.get`` and a default, so the step *succeeds* whether the object carries a mirror
    ref or not — which is the case worth catching. A step that only trips the wire when the mirror
    happens to be populated would let the violation ship on any branch where it is not.
    """
    for uid, document in context.lifecycle_projection().items():
        refs = document.get("external_refs", {})
        return f"read {uid}.external_refs = {refs}"
    return "no objects"


def _rogue_gh(context: Context) -> str:
    """A 'lifecycle' step that shells out to gh. On a bare remote there is nothing there to ask."""
    conformance.subprocess.run(["gh", "issue", "view", "1400"], capture_output=True, timeout=60)
    return "shelled out to gh"


def test_c002_integration_001_fails_when_lifecycle_reads_provider(tmp_path) -> None:
    """A step that consults the registry is named, and the run is failed, though the step passed."""
    context = conformance.setup(tmp_path)
    steps = (*conformance.STEPS, Step("rogue-registry", _rogue_registry))

    report = conformance.run(context, steps=steps)

    # Every step SUCCEEDED — including the rogue one. Nothing raised, nothing errored.
    assert report.failed == [], f"no step failed; the boundary is what failed: {report.render()}"
    assert all(result.ok for result in report.results)

    # And the run still fails, because of what the step touched to succeed.
    assert not report.ok
    assert report.violations
    assert any("rogue-registry" in violation for violation in report.violations)
    assert any("provider registry" in violation for violation in report.violations)
    assert all("I7" in violation for violation in report.violations)
    assert conformance.INVARIANT_I7 in report.render()


def test_c002_integration_001_fails_when_a_step_reads_external_refs(tmp_path) -> None:
    """Reading the mirror to decide something is the violation, whatever the decision was."""
    context = conformance.setup(tmp_path)
    steps = (*conformance.STEPS, Step("rogue-external-refs", _rogue_external_refs))

    report = conformance.run(context, steps=steps)

    assert not report.ok
    assert report.failed == []
    assert any("rogue-external-refs" in v and "external_refs" in v for v in report.violations)
    assert any("I7" in violation for violation in report.violations)


def test_c002_integration_001_fails_when_a_step_shells_out_to_gh(tmp_path) -> None:
    """The remote is bare, so `gh` could tell it nothing — the sin is reaching for it at all."""
    context = conformance.setup(tmp_path)
    steps = (*conformance.STEPS, Step("rogue-gh", _rogue_gh))

    report = conformance.run(context, steps=steps)

    assert not report.ok
    assert any("gh" in violation for violation in report.violations)
    assert any("issue view 1400" in violation for violation in report.violations), (
        "the tripwire records WHAT was asked of gh, not merely that something was"
    )
