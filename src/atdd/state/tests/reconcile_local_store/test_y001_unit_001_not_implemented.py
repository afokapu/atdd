# URN: test:reconcile-local-store:archive-overlay-events:Y001-UNIT-001-not-implemented
# Acceptance: acc:reconcile-local-store:Y001-UNIT-001-not-implemented
# WMBT: wmbt:reconcile-local-store:Y001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the hazard half of overlay-event-replayed-twice — an event whose effect the incoming projection already carries is marked committed and NOT re-applied, so a developer's own merged work does not come back and overwrite what they did next. Refs #1400.
"""An event the shared truth already carries must not replay again (Y001-UNIT-001).

wagon: reconcile-local-store | feature: archive-overlay-events | phase: RED
WMBT: wmbt:reconcile-local-store:Y001

This is the hazard the WMBT is named for. B authors a transition, projects it, commits
it, merges it, and pulls. The event is still sitting in B's overlay — so a reconcile that
replays every event it finds would apply B's *old* intent on top of the *new* shared
truth, silently reverting whatever happened to that object in between.

Worse, it would do so quietly and forever: the event is never drained, so every future
reconcile replays it again. The fix is that an event is replayed only while the shared
truth does not yet reflect it. Once it does, the event is committed and done. Refs #1400.
"""
from __future__ import annotations

from atdd.state import authoring, overlay
from atdd.state.reconcile import hydrate_store, reconcile

from ._helpers import UID_A, checkout, commit_all, document, store, write_projection


def test_y001_unit_001_not_implemented(tmp_path) -> None:
    """A landed event is marked committed, not replayed a second time."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED", owner="dev-b")])
    commit_all(repo, "base projection")
    hydrate_store(repo)

    # B authors a transition PLANNED → GREEN locally.
    conn = store(repo)
    try:
        transition = authoring.request_transition(conn, UID_A, "GREEN")
    finally:
        conn.close()

    # B projects it, commits it, pushes it, and it merges. B now pulls: the incoming
    # projection carries B's own transition, come back around through the shared truth.
    write_projection(repo, [document(UID_A, phase="GREEN", owner="dev-b")])
    commit_all(repo, "B's transition merged")

    landed = reconcile(repo)

    # The event is recognised as already carried, and retired instead of replayed.
    assert landed.already_committed == [transition.event_id]
    assert landed.replayed == []

    conn = store(repo)
    try:
        # It leaves the replayable set for good — the id is stable, never re-minted.
        event = overlay.events_for(conn, UID_A)[0]
        assert event.event_id == transition.event_id
        assert event.status == overlay.STATUS_COMMITTED
        assert overlay.replayable_events(conn) == []
        assert overlay.is_dirty(conn) is False
    finally:
        conn.close()

    # Now the hazard itself. A peer advances the object past B's transition. If the
    # retired event replayed a second time, it would drag the object back from SMOKE to
    # B's stale GREEN — reverting the peer's work, silently, on every future reconcile.
    write_projection(repo, [document(UID_A, phase="SMOKE", owner="dev-a")])
    commit_all(repo, "a peer advances it past B's transition")

    again = reconcile(repo)
    assert again.mode == "hydrate"   # there is no overlay left to replay
    assert again.replayed == []
    assert again.already_committed == []

    conn = store(repo)
    try:
        row = conn.execute("SELECT state FROM objects WHERE uid=?", (UID_A,)).fetchone()
        assert row["state"] == "SMOKE", "the retired overlay event replayed and reverted the peer"
        assert overlay.events_for(conn, UID_A)[0].status == overlay.STATUS_COMMITTED
    finally:
        conn.close()
