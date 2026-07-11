# URN: test:reconcile-local-store:guard-dirty-store:C001-UNIT-001-dirty-store-is-backed-up-not-overwritten
# Acceptance: acc:reconcile-local-store:C001-UNIT-001-dirty-store-is-backed-up-not-overwritten
# WMBT: wmbt:reconcile-local-store:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: a store with non-empty overlay_events is classified dirty and its overlay count surfaced; state.sqlite is backed up before any mutation and the backup path returned; the gate routes to backup-hydrate-replay, never to plain hydrate-overwrite. Refs #1400.
"""A dirty store is backed up and replayed, never overwritten (C001-UNIT-001).

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C001

Reconcile is not overwrite (I5). A store carrying uncommitted overlay is holding a
developer's private, unshared, unrecoverable work — so before anything else,
reconcile classifies it dirty, copies it aside, and routes to the replay path. The
backup comes *before* the first mutation, which is what makes the guarantee
unconditional: even a reconcile that crashes halfway leaves an undo behind. Refs #1400.
"""
from __future__ import annotations

from atdd.state import authoring, overlay
from atdd.state.reconcile import ReconcileResult, backup_store, reconcile

from ._helpers import (
    UID_A,
    checkout,
    commit_all,
    document,
    store,
    store_bytes,
    store_file,
    write_projection,
)


def test_c001_unit_001_dirty_store_is_backed_up_not_overwritten(tmp_path) -> None:
    """The store is reported dirty, backed up before any mutation, and routed to replay."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED")])
    base = commit_all(repo, "base projection")

    from atdd.state.reconcile import hydrate_store

    hydrate_store(repo)

    # The developer authors privately: the store now carries uncommitted overlay.
    conn = store(repo)
    try:
        created = authoring.create_object(conn, slug="feature-y", owner_actor="dev-b")

        # The store is classified dirty and the overlay event count is surfaced.
        assert overlay.is_dirty(conn) is True
        events = overlay.replayable_events(conn)
        assert len(events) == 1
        assert events[0].event_id == created.event_id
    finally:
        conn.close()

    # A peer's work lands at a new HEAD.
    write_projection(repo, [document(UID_A, phase="PLANNED"), document("wi_01HF7YAT00M78607F0000000C3")])
    new_head = commit_all(repo, "peer work")

    before = store_bytes(repo)
    result = reconcile(repo)

    # The gate selected the backup-hydrate-replay path, never plain hydrate-overwrite.
    assert isinstance(result, ReconcileResult)
    assert result.mode == "replay"
    assert result.base_commit == base
    assert result.head == new_head
    assert result.replayed == [created.event_id]

    # A backup of state.sqlite was written and its path returned.
    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert result.backup_path.read_bytes() == before  # taken BEFORE any mutation

    # The private work survived, and the peer's object arrived.
    conn = store(repo)
    try:
        assert conn.execute(
            "SELECT 1 FROM objects WHERE uid=?", (created.object_uid,),
        ).fetchone() is not None
        assert conn.execute(
            "SELECT 1 FROM objects WHERE uid=?", ("wi_01HF7YAT00M78607F0000000C3",),
        ).fetchone() is not None
    finally:
        conn.close()

    # The backup writer never destroys an earlier undo: a second backup is a new file.
    second = backup_store(store_file(repo))
    assert second != result.backup_path
    assert result.backup_path.exists()
