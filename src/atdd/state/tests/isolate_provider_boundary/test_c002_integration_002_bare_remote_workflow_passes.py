# URN: test:isolate-provider-boundary:verify-remote-conformance:C002-INTEGRATION-002-bare-remote-workflow-passes
# Acceptance: acc:isolate-provider-boundary:C002-INTEGRATION-002-bare-remote-workflow-passes
# WMBT: wmbt:isolate-provider-boundary:C002
# Phase: GREEN
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: The M5 exit criterion: every step of the workflow — mint, project, commit, push, hydrate, reconcile, canonicality, CI merge authority, import boundary — completes against a BARE git remote with zero providers registered; the committed projection is byte-identical to project(store); and no GitHub API call, gh invocation, provider consultation or external_refs read occurs anywhere in the run. Refs #1400.
"""The whole workflow, against a bare remote, with nothing installed (C002-INTEGRATION-002).

wagon: isolate-provider-boundary | feature: verify-remote-conformance | phase: GREEN
WMBT: wmbt:isolate-provider-boundary:C002

This is milestone M5's exit criterion, executed: *core completes its full workflow with zero
providers against a bare git remote.* The remote is ``git init --bare`` — object storage, no API,
no token, nothing to call. A developer authors an object, projects it, commits it with trailers,
pushes; a second developer hydrates a store from the projection at HEAD and reconciles; the CI
merge-authority gate runs its seven required checks over what landed. All of it on git alone.

"No GitHub API call occurred" is asserted three ways, because a bare assertion of a negative is
worth very little: the registry was never consulted (its entry point was a tripwire), no step read
``external_refs`` through the view core hands it, and ``gh`` — first on ``PATH``, as a shim that
records and fails — was never reached for.
"""
from __future__ import annotations

from atdd.state import conformance, provider_seam
from atdd.state.projection import canonical_bytes, read_projection


def test_c002_integration_002_bare_remote_workflow_passes(tmp_path) -> None:
    """Every step completes with zero providers; the projection is canonical; nobody called GitHub."""
    assert provider_seam.registered_names() == [], "the M5 claim is about ZERO providers"

    context = conformance.setup(tmp_path)
    report = conformance.run(context)

    assert report.ok, report.render()
    assert report.failed == []

    # Every step of the workflow ran, and each one passed.
    ran = [result.name for result in report.results]
    assert ran == ["mint", "project", "commit", "push", "hydrate", "reconcile",
                   "canonicality", "ci", "import-boundary"]
    assert all(result.ok for result in report.results)

    # The gate that decides whether a branch may land ran its full required-check set.
    ci = next(result for result in report.results if result.name == "ci")
    assert "7 required check(s)" in ci.report

    # The committed projection is byte-identical to project(store) — I1, over what was pushed to a
    # remote that has never heard of ATDD.
    documents = read_projection(context.peer / ".atdd" / "state" / "projection")
    assert documents, "the peer hydrated from a projection that actually arrived"
    for uid, document in documents.items():
        committed = (context.peer / ".atdd" / "state" / "projection" / f"{uid}.yaml").read_bytes()
        assert committed == canonical_bytes(document)

    # No provider was consulted, no external_refs was read, and gh was never reached for.
    assert context.tripwire.clean
    assert context.tripwire.provider_touches == []
    assert context.tripwire.external_ref_reads == []
    assert context.tripwire.gh_invocations == []
    assert report.violations == []

    # And the remote really is bare: it is a git directory with no working tree, which is why
    # there was no API there to call even if a step had wanted one.
    assert (context.remote / "HEAD").is_file()
    assert not (context.remote / ".git").exists()
    assert provider_seam.registered_names() == []
