# URN: test:reconcile-local-store:archive-overlay-events:Y001-SMOKE-001-overlay-event-replayed-twice
# Acceptance: acc:reconcile-local-store:Y001-SMOKE-001-overlay-event-replayed-twice
# WMBT: wmbt:reconcile-local-store:Y001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — through the real CLI, an overlay event whose work has come back through the shared truth is marked committed and never replayed again, so repeated real reconciles cannot revert a peer's later work. Refs #1400.
"""SMOKE — an event is replayed once, ever (Y001-SMOKE-001).

wagon: reconcile-local-store | feature: archive-overlay-events | phase: SMOKE
WMBT: wmbt:reconcile-local-store:Y001

Driven through the real CLI against a real store, because the failure mode this guards is
one that only shows up over *time*: an event that never drains gets replayed by every
future reconcile, silently reverting the same object again and again. So this runs
reconcile repeatedly and insists the object stays where the shared truth put it. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import overlay

from ._helpers import UID_A, checkout, commit_all, document, store, write_projection
from ._live import atdd_state


@pytest.mark.smoke
def test_y001_smoke_001_overlay_event_replayed_twice(tmp_path) -> None:
    """A landed event retires for good — repeated real reconciles never resurrect it."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED", owner="dev-b")])
    commit_all(repo, "base projection")
    assert atdd_state(repo, "hydrate").returncode == 0

    # B authors a transition PLANNED → GREEN through the real CLI.
    authored = atdd_state(repo, "author", "transition", UID_A, "--to", "GREEN")
    assert authored.returncode == 0, authored.stderr

    conn = store(repo)
    try:
        event_id = overlay.events_for(conn, UID_A)[0].event_id
        assert overlay.is_dirty(conn) is True
    finally:
        conn.close()

    # B projects and commits it: the work is now in the shared truth.
    assert atdd_state(repo, "project").returncode == 0
    commit_all(repo, "B's transition merged")

    assert atdd_state(repo, "reconcile").returncode == 0

    # The event is retired — committed, and out of the replayable set for good.
    conn = store(repo)
    try:
        event = overlay.events_for(conn, UID_A)[0]
        assert event.event_id == event_id      # the id is stable, never re-minted
        assert event.status == overlay.STATUS_COMMITTED
        assert event.projection_digest is not None  # it knows which projection carried it
        assert overlay.replayable_events(conn) == []
        assert overlay.is_dirty(conn) is False
    finally:
        conn.close()

    # A peer now advances the object PAST B's transition, twice over. If B's retired
    # event ever replayed again, it would drag the object back to GREEN each time.
    for phase in ("SMOKE", "REFACTOR"):
        write_projection(repo, [document(UID_A, phase=phase, owner="dev-a")])
        commit_all(repo, f"peer advances to {phase}")

        reconciled = atdd_state(repo, "reconcile")
        assert reconciled.returncode == 0, reconciled.stdout + reconciled.stderr

        conn = store(repo)
        try:
            row = conn.execute("SELECT state FROM objects WHERE uid=?", (UID_A,)).fetchone()
            assert row["state"] == phase, "the retired overlay event replayed and reverted the peer"
        finally:
            conn.close()

    # The event is still on the books as an audit record — retired, not deleted.
    conn = store(repo)
    try:
        assert [e.event_id for e in overlay.all_events(conn)] == [event_id]
        assert overlay.all_events(conn)[0].status == overlay.STATUS_COMMITTED
    finally:
        conn.close()
