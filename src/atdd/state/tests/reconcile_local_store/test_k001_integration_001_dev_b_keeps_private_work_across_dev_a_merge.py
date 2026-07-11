# URN: test:reconcile-local-store:verify-collaboration-flow:K001-INTEGRATION-001-dev-b-keeps-private-work-across-dev-a-merge
# Acceptance: acc:reconcile-local-store:K001-INTEGRATION-001-dev-b-keeps-private-work-across-dev-a-merge
# WMBT: wmbt:reconcile-local-store:K001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: over a bare git remote with no provider, Dev B pulls Dev A's merged projection through Git alone; git merges the disjoint per-uid files without conflict; B's store becomes hydrate(new HEAD) + replay(B's overlay); B's uncommitted feature-y survives and B's store_base_commit equals the new HEAD. Refs #1400.
"""The problem this whole wagon exists to solve (K001-INTEGRATION-001).

wagon: reconcile-local-store | feature: verify-collaboration-flow | phase: RED
WMBT: wmbt:reconcile-local-store:K001

Dev A merges. Dev B pulls. B's local store must pick up A's work *and* keep B's own
uncommitted authoring — work that exists nowhere else in the world: not on the remote,
not in a projection file, not in a peer's checkout. Losing it is unrecoverable, and
"just don't have uncommitted work when you pull" is not a workflow anyone follows.

The proof is in the fixture, not the assertions. The remote is **bare git** — no GitHub,
no API, no provider, nothing but object storage — and a socket tripwire fails the test if
anything reaches for the network. If the flow completes here, the hot path is
provider-free as a matter of fact rather than of intent (I7). Refs #1400.
"""
from __future__ import annotations

import socket

import pytest

from atdd.state import authoring, metadata, overlay
from atdd.state.projection import project
from atdd.state.reconcile import hydrate_store, projection_path, reconcile
from atdd.state.store import StateStore

from ._helpers import store
from ._live import commit, commit_push, git_tracked, head, pull, two_developers


@pytest.fixture(autouse=True)
def no_network(monkeypatch) -> None:
    """Fail loudly if anything opens a socket. The collaboration path must be pure git."""

    def _refuse(self, address):  # noqa: ANN001 — a socket.connect stand-in
        raise AssertionError(f"the collaboration flow attempted a network call: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", _refuse)


def _project_and_push(repo, message: str) -> str:
    conn = store(repo)
    try:
        result = project(StateStore(conn), projection_path(repo))
        overlay.mark_projected(conn, result.digest)
    finally:
        conn.close()
    return commit_push(repo, message)


def test_k001_integration_001_dev_b_keeps_private_work_across_dev_a_merge(tmp_path) -> None:
    """B pulls A's merged work through git alone, and B's private feature-y survives."""
    _remote, dev_a, dev_b = two_developers(tmp_path)

    # Both developers hydrate from the main projection.
    hydrate_store(dev_a)
    hydrate_store(dev_b)

    # A authors feature-x, projects it, commits it and merges it to main.
    conn = store(dev_a)
    try:
        feature_x = authoring.create_object(conn, slug="feature-x", owner_actor="dev-a").object_uid
        authoring.request_transition(conn, feature_x, "PLANNED")
    finally:
        conn.close()
    _project_and_push(dev_a, "A: feature-x")

    # B concurrently authors feature-y and leaves it UNCOMMITTED in the overlay: it is
    # in no projection file, on no remote, in no other checkout.
    conn = store(dev_b)
    try:
        feature_y = authoring.create_object(conn, slug="feature-y", owner_actor="dev-b").object_uid
        b_events = [e.event_id for e in overlay.replayable_events(conn)]
        assert b_events, "B's private work must be in the overlay"
    finally:
        conn.close()

    # B has an unrelated local commit, so the pull is a real merge, not a fast-forward.
    (dev_b / "notes.md").write_text("b's notes\n", encoding="utf-8")
    commit(dev_b, "B: unrelated local commit")

    # B pulls. Git merges the disjoint per-uid projection files without conflict —
    # one file per object is precisely what makes concurrent authoring mergeable.
    new_head = pull(dev_b)
    assert new_head == head(dev_b)
    assert (projection_path(dev_b) / f"{feature_x}.yaml").exists()

    # The HEAD-change hook runs `atdd state reconcile`.
    result = reconcile(dev_b)
    assert result.mode == "replay"
    assert result.head == new_head
    assert result.replayed == b_events

    conn = store(dev_b)
    try:
        objects = {
            row["uid"]: row["state"]
            for row in conn.execute("SELECT uid, state FROM objects WHERE kind='work_item'")
        }

        # B's store equals hydrate(new HEAD projection) ...
        assert objects[feature_x] == "PLANNED"          # B sees A's feature-x state
        # ... with B's overlay replayed on top: B's uncommitted feature-y is still there.
        assert feature_y in objects
        assert StateStore(conn).objects.get(feature_y).data["slug"] == "feature-y"

        # B's store_base_commit equals the new HEAD.
        assert metadata.base_commit(conn) == new_head
    finally:
        conn.close()

    # B learned A's state through Git and the projection alone. No GitHub was read: the
    # socket tripwire above would have failed the test, and the remote has no API at all.
    #
    # And the store itself was never shared — it is the private authoring workspace, so
    # it must never be a tracked file. If it were, B's private overlay would have been
    # pushed to the remote and this whole exercise would be moot.
    tracked = git_tracked(dev_b)
    assert not [path for path in tracked if path.endswith("state.sqlite")]
    assert f".atdd/state/projection/{feature_x}.yaml" in tracked
