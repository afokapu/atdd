# URN: test:reconcile-local-store:verify-collaboration-flow:K001-SMOKE-001-collaboration-flow-runs-against-bare-remote
# Acceptance: acc:reconcile-local-store:K001-SMOKE-001-collaboration-flow-runs-against-bare-remote
# WMBT: wmbt:reconcile-local-store:K001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the scripted A/B flow (hydrate, author, project, commit, push, merge, pull, reconcile) runs entirely through real subprocess invocations of the installed atdd CLI against a real bare git remote, with zero providers registered, B's private overlay intact, B's store_base_commit at the new HEAD, and no SQLite committed. Refs #1400.
"""SMOKE — the whole collaboration flow, real CLI, real bare remote (K001-SMOKE-001).

wagon: reconcile-local-store | feature: verify-collaboration-flow | phase: SMOKE
WMBT: wmbt:reconcile-local-store:K001

Every command below is a real subprocess invocation of the real ``atdd`` CLI against real
git clones of a real bare remote. Nothing is patched, stubbed or faked.

That is the claim worth proving. The model says collaboration happens through git and the
committed projection alone — so a remote with *no API at all* should be sufficient. Here
it is: a bare repository on disk, and the full A/B flow completing over it. Refs #1400.
"""
from __future__ import annotations

import pytest

from ._live import atdd_state, commit, commit_push, git_tracked, head, pull, two_developers


@pytest.mark.smoke
def test_k001_smoke_001_collaboration_flow_runs_against_bare_remote(tmp_path) -> None:
    """hydrate → author → project → commit → push → merge → pull → reconcile, all for real."""
    _remote, dev_a, dev_b = two_developers(tmp_path)

    # Both developers hydrate from main's projection through the real CLI.
    for dev in (dev_a, dev_b):
        hydrated = atdd_state(dev, "hydrate")
        assert hydrated.returncode == 0, hydrated.stderr

    # A authors feature-x, projects it, commits and pushes it to main.
    created = atdd_state(dev_a, "object", "create", "--slug", "feature-x", "--owner", "dev-a")
    assert created.returncode == 0, created.stderr
    feature_x = created.stdout.strip()

    moved = atdd_state(dev_a, "author", "transition", feature_x, "--to", "PLANNED")
    assert moved.returncode == 0, moved.stderr

    projected = atdd_state(dev_a, "project")
    assert projected.returncode == 0, projected.stderr
    commit_push(dev_a, "A: feature-x")

    # B authors feature-y and leaves it UNCOMMITTED in the overlay.
    created_b = atdd_state(dev_b, "object", "create", "--slug", "feature-y", "--owner", "dev-b")
    assert created_b.returncode == 0, created_b.stderr
    feature_y = created_b.stdout.strip()

    dirty = atdd_state(dev_b, "overlay")
    assert dirty.returncode == 0
    assert feature_y in dirty.stdout

    # B has an unrelated local commit, so the pull is a genuine merge.
    (dev_b / "notes.md").write_text("b's notes\n", encoding="utf-8")
    commit(dev_b, "B: unrelated local commit")

    # B pulls A's merged work — git merges the disjoint per-uid files without conflict.
    new_head = pull(dev_b)
    assert new_head == head(dev_b)
    assert (dev_b / ".atdd" / "state" / "projection" / f"{feature_x}.yaml").exists()

    # B's store is stale until it reconciles, and the CLI says so.
    stale = atdd_state(dev_b, "freshness")
    assert stale.returncode == 1
    assert "STALE" in stale.stdout

    # The HEAD-change hook's command: `atdd state reconcile`.
    reconciled = atdd_state(dev_b, "reconcile")
    assert reconciled.returncode == 0, reconciled.stdout + reconciled.stderr
    assert "replay" in reconciled.stdout

    # B's private overlay survived A's merge: feature-y is still in B's store.
    assert (dev_b / ".atdd" / "state" / "projection" / f"{feature_y}.yaml").exists()

    # B's store_base_commit equals the new HEAD.
    fresh = atdd_state(dev_b, "freshness")
    assert fresh.returncode == 0, fresh.stdout
    assert "fresh" in fresh.stdout
    assert new_head[:12] in fresh.stdout

    # B sees A's feature-x through git alone — no provider was ever registered, and the
    # remote is a bare repository with no API to call.
    projected_b = atdd_state(dev_b, "project")
    assert projected_b.returncode == 0, projected_b.stderr
    assert feature_x in projected_b.stdout
    assert feature_y in projected_b.stdout

    # The run completes with no committed SQLite store: it is the private workspace.
    tracked = git_tracked(dev_b)
    assert not [path for path in tracked if "state.sqlite" in path]
    assert f".atdd/state/projection/{feature_x}.yaml" in tracked
