# URN: test:reconcile-local-store:reconcile-store-state:R001-UNIT-002-invalid-replay-does-not-advance-base
# Acceptance: acc:reconcile-local-store:R001-UNIT-002-invalid-replay-does-not-advance-base
# WMBT: wmbt:reconcile-local-store:R001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: an overlay event that no longer applies to the incoming public state stops the replay at the first invalid event, leaves store_base_commit at B, and discards the partially replayed store without ever persisting it. Refs #1400.
"""An invalid replay advances nothing (R001-UNIT-002).

wagon: reconcile-local-store | feature: reconcile-store-state | phase: RED
WMBT: wmbt:reconcile-local-store:R001

The overlay was authored against the *old* public state. When the incoming projection
has moved out from under it — here, the shared truth tombstoned the very object the
developer is still transitioning — the event no longer means what it meant, and the
events queued behind it were authored against a state that never existed. So the
replay stops at the first invalid event rather than applying what it can.

Advancing the anchor after a partial replay would be the real damage: the store would
claim to be hydrate(H) + replay(overlay) while actually holding neither. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import authoring, metadata, overlay
from atdd.state.projection import STATE_TOMBSTONED, read_projection
from atdd.state.reconcile import ReplayConflictError, hydrate_store, reconcile

from ._helpers import (
    UID_A,
    checkout,
    commit_all,
    document,
    projection_dir,
    store,
    store_bytes,
    write_projection,
)


def test_r001_unit_002_invalid_replay_does_not_advance_base(tmp_path) -> None:
    """The replay stops at the first invalid event; base stays B; nothing is persisted."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED", owner="dev-a")])
    base = commit_all(repo, "base projection")
    hydrate_store(repo)

    # The developer requests a transition on UID_A, then does more local work behind it.
    conn = store(repo)
    try:
        transition = authoring.request_transition(conn, UID_A, "GREEN")
        trailing = authoring.update_train(conn, UID_A, "train:commons:spine")
    finally:
        conn.close()

    # Meanwhile the shared truth TOMBSTONED that very object.
    write_projection(
        repo,
        [document(UID_A, phase="PLANNED", state=STATE_TOMBSTONED, owner="dev-a",
                  tombstone={"reason": "superseded"})],
    )
    commit_all(repo, "peer tombstoned it")

    before = store_bytes(repo)
    projection_before = read_projection(projection_dir(repo))

    with pytest.raises(ReplayConflictError) as stopped:
        reconcile(repo)

    # The replay stopped at the FIRST invalid event — the trailing one was never judged.
    report = stopped.value.report
    assert [c.event.event_id for c in report.conflicts] == [transition.event_id]
    assert trailing.event_id not in {c.event.event_id for c in report.conflicts}
    assert "TOMBSTONED" in report.conflicts[0].reason

    # store_base_commit remains B.
    conn = store(repo)
    try:
        assert metadata.base_commit(conn) == base

        # The partially replayed store is discarded and never persisted: the object
        # still holds its pre-reconcile phase, and the overlay is untouched.
        row = conn.execute("SELECT state FROM objects WHERE uid=?", (UID_A,)).fetchone()
        assert row["state"] == "GREEN"  # the LOCAL pre-reconcile state, not the incoming
        assert [e.event_id for e in overlay.replayable_events(conn)] == [
            transition.event_id, trailing.event_id,
        ]
    finally:
        conn.close()

    # And nothing at all was written: state.sqlite is byte-identical, and the
    # projection on disk was not re-projected.
    assert store_bytes(repo) == before
    assert read_projection(projection_dir(repo)) == projection_before
