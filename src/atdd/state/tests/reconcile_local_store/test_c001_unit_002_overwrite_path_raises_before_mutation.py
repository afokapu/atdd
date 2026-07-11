# URN: test:reconcile-local-store:guard-dirty-store:C001-UNIT-002-overwrite-path-raises-before-mutation
# Acceptance: acc:reconcile-local-store:C001-UNIT-002-overwrite-path-raises-before-mutation
# WMBT: wmbt:reconcile-local-store:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the hydrate-overwrite path raises DirtyStoreError naming the overlay events that would be lost, leaves state.sqlite byte-identical, and still hydrates a clean store with no backup. Refs #1400.
"""The overwrite path raises before it touches sqlite (C001-UNIT-002).

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C001

``hydrate(incoming)`` replaces the store's public half wholesale. Against a clean
store that is exactly right. Against a *dirty* one it would silently discard work that
exists nowhere else — not in the projection, not on the remote, not in a peer's
checkout. So the overwrite path refuses, and it refuses *before* the first write, so
there is nothing to undo. The refusal names the events at stake: an operator deciding
what to do next needs to know what they would be losing. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import authoring, overlay
from atdd.state.reconcile import DirtyStoreError, hydrate_store

from ._helpers import UID_A, UID_B, checkout, commit_all, document, store, store_bytes, write_projection


def test_c001_unit_002_overwrite_path_raises_before_mutation(tmp_path) -> None:
    """A dirty store refuses the overwrite; a clean one hydrates with no backup."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED")])
    commit_all(repo, "base projection")

    # The clean-store case still hydrates without a backup.
    hydrated, base = hydrate_store(repo)
    assert hydrated == 1
    assert not list(repo.glob(".atdd/state/*.bak*")), "a clean hydrate must not back up"

    # Now make it dirty with two uncommitted authoring events.
    conn = store(repo)
    try:
        created = authoring.create_object(conn, slug="feature-y", owner_actor="dev-b")
        moved = authoring.request_transition(conn, created.object_uid, "PLANNED")
        assert overlay.is_dirty(conn) is True
    finally:
        conn.close()

    write_projection(repo, [document(UID_A, phase="GREEN"), document(UID_B)])
    commit_all(repo, "incoming")
    before = store_bytes(repo)

    # The caller invokes the overwrite path directly.
    with pytest.raises(DirtyStoreError) as refused:
        hydrate_store(repo)

    # A DirtyStoreError is raised naming the overlay events that would be lost.
    assert {e.event_id for e in refused.value.events} == {created.event_id, moved.event_id}
    message = str(refused.value)
    assert overlay.OBJECT_CREATED in message
    assert overlay.PHASE_TRANSITION_REQUESTED in message
    assert created.object_uid in message
    assert "reconcile" in message  # it names the path that does NOT lose the work

    # state.sqlite is byte-identical to its pre-call content.
    assert store_bytes(repo) == before

    # And nothing was hydrated: the store still holds the base projection's phase.
    conn = store(repo)
    try:
        row = conn.execute("SELECT state FROM objects WHERE uid=?", (UID_A,)).fetchone()
        assert row["state"] == "PLANNED"  # not the incoming GREEN
        assert conn.execute("SELECT 1 FROM objects WHERE uid=?", (UID_B,)).fetchone() is None
        from atdd.state import metadata

        assert metadata.base_commit(conn) == base  # the anchor did not advance
    finally:
        conn.close()
