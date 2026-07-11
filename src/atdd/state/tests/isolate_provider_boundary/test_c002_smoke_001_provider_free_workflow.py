# URN: test:isolate-provider-boundary:verify-remote-conformance:C002-SMOKE-001-provider-free-workflow
# Acceptance: acc:isolate-provider-boundary:C002-SMOKE-001-provider-free-workflow
# WMBT: wmbt:isolate-provider-boundary:C002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: The real `atdd state conformance` CLI, run by subprocess in a real checkout with a real state.sqlite and zero providers, drives the entire workflow against a bare remote and exits 0 — and the real `atdd state object create / project / canonicality / merge-authority` verbs each complete with a `gh` tripwire first on PATH that is never touched. No mocks, no manual patching. Refs #1400.
"""The provider-free workflow is a command, and it passes (C002-SMOKE-001).

wagon: isolate-provider-boundary | feature: verify-remote-conformance | phase: SMOKE
WMBT: wmbt:isolate-provider-boundary:C002

The M5 exit criterion, driven the way an operator or a CI job would drive it: one command, a real
exit code. Then the same claim again the long way — each lifecycle verb of the workflow run
separately through the real CLI against a real ``.atdd/state/state.sqlite`` — because "the
conformance command passes" and "the commands the conformance command wraps pass" are different
statements, and a wagon whose exit criterion is the first one had better be able to show the second.

Throughout, ``gh`` is first on ``PATH`` as a shim that records its arguments and exits 127. Nothing
in this test ever touches it. That is the assertion: not that GitHub answered unhelpfully, but that
core never asked.
"""
from __future__ import annotations

import pytest

from ._live import (
    atdd_state,
    clone,
    commit_projection,
    gh_was_invoked,
    git,
    repo_on_bare_remote,
    seed_object,
)


@pytest.mark.smoke
def test_c002_smoke_001_provider_free_workflow(tmp_path) -> None:
    """The real CLI drives the whole workflow against a bare remote with zero providers."""
    remote, repo = repo_on_bare_remote(tmp_path)

    # Zero providers — the configuration core ships in.
    providers = atdd_state(repo, "providers")
    assert providers.returncode == 0
    assert "no SyncProvider is registered" in providers.stdout

    # One command: the entire workflow against a bare remote.
    run = atdd_state(repo, "conformance", "--work", str(tmp_path / "conformance"))

    assert run.returncode == 0, run.stdout + run.stderr
    assert "provider-free conformance PASSED" in run.stdout
    assert "0 providers" in run.stdout
    for step in ("mint", "project", "commit", "push", "hydrate", "reconcile", "ci"):
        assert f"[PASS] {step}" in run.stdout, f"the step {step!r} did not pass:\n{run.stdout}"

    # Now the long way, through the real verbs against a real store, in this real checkout.
    uid = seed_object(repo)
    assert (repo / ".atdd" / "state" / "state.sqlite").is_file(), "a real State Store, not a mock"

    canonical = atdd_state(repo, "canonicality")
    assert canonical.returncode == 0, canonical.stdout + canonical.stderr

    digest = atdd_state(repo, "digest")
    assert digest.returncode == 0
    assert digest.stdout.strip().startswith("sha256:")

    # The author's object is still private work — uncommitted overlay — so hydrating over it would
    # destroy it, and core refuses (I5). That refusal is the workflow talking, not a fault: the way
    # to share private work is to project it, commit it, and push it.
    dirty = atdd_state(repo, "hydrate")
    assert dirty.returncode != 0
    assert "uncommitted overlay" in dirty.stdout

    commit_projection(repo, uid)
    git(repo, "push", "--quiet", "origin", "main")

    gate = atdd_state(repo, "merge-authority", "--actor", "core-lifecycle")
    assert gate.returncode == 0, gate.stdout + gate.stderr
    assert "merge-authority run PASSED" in gate.stdout

    # A SECOND developer clones the bare remote and builds their store from the projection at HEAD
    # — the §11 collaboration flow, and the whole thing they learn about the object comes out of
    # git. There is no other source; the remote has none to offer.
    peer = clone(remote, tmp_path / "peer")
    hydrated = atdd_state(peer, "hydrate")

    assert hydrated.returncode == 0, hydrated.stdout + hydrated.stderr
    assert uid in hydrated.stdout
    assert (peer / ".atdd" / "state" / "state.sqlite").is_file()

    reconciled = atdd_state(peer, "reconcile")
    assert reconciled.returncode == 0, reconciled.stdout + reconciled.stderr

    boundary = atdd_state(repo, "import-boundary")
    assert boundary.returncode == 0, boundary.stdout + boundary.stderr

    # Not once, in any of it, did core reach for the GitHub CLI.
    assert gh_was_invoked(repo) == []
