# URN: test:reconcile-local-store:archive-overlay-events:Y001-UNIT-002-holds
# Acceptance: acc:reconcile-local-store:Y001-UNIT-002-holds
# WMBT: wmbt:reconcile-local-store:Y001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: each overlay event has a stable event_id and a status (pending/projected/committed/discarded/conflicted); projecting records WHICH projection represents an event; and only pending or projected-but-uncommitted events are replayed. Refs #1400.
"""The event lifecycle that makes replay-once decidable (Y001-UNIT-002).

wagon: reconcile-local-store | feature: archive-overlay-events | phase: RED
WMBT: wmbt:reconcile-local-store:Y001

"Replay it only once" is not a rule you can enforce without a way to *name* an event and
a way to say *where it got to*. So each event carries a stable id, minted once and never
re-minted, and a status that only moves forward.

The subtle one is ``projected``. A projected event is still replayable, because a file on
disk is not yet shared truth — the developer could still discard it, or the merge could
still be rejected. It becomes ``committed`` only when the incoming projection actually
carries it. The projection *digest* is recorded on the event so the store can recognise
its own work coming back. Refs #1400.
"""
from __future__ import annotations

import sqlite3

import pytest

from atdd.state import authoring, overlay
from atdd.state.db import apply_migrations
from atdd.state.projection import project
from atdd.state.store import StateStore


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    apply_migrations(connection)
    yield connection
    connection.close()


def test_y001_unit_002_holds(tmp_path, conn) -> None:
    """Stable ids, a forward-only status, a projection back-reference, replay-once."""
    created = authoring.create_object(conn, slug="feature-y", owner_actor="dev-b")
    uid = created.object_uid
    moved = authoring.request_transition(conn, uid, "PLANNED")

    # Each event has a stable event_id — distinct, and unchanged by anything that
    # happens to it later.
    ids = [created.event_id, moved.event_id]
    assert len(set(ids)) == 2
    assert all(event_id.startswith("ev_") for event_id in ids)
    assert [e.event_id for e in overlay.all_events(conn)] == ids

    # The five statuses are the vocabulary, and a fresh event starts pending.
    assert overlay.STATUSES == ("pending", "projected", "committed", "discarded", "conflicted")
    assert all(e.status == overlay.STATUS_PENDING for e in overlay.all_events(conn))
    assert [e.event_id for e in overlay.replayable_events(conn)] == ids

    # Projecting records WHICH projection represents the events — the back-reference.
    result = project(StateStore(conn), tmp_path / "projection")
    overlay.mark_projected(conn, result.digest)

    projected = overlay.all_events(conn)
    assert all(e.status == overlay.STATUS_PROJECTED for e in projected)
    assert all(e.projection_digest == result.digest for e in projected)
    assert [e.event_id for e in projected] == ids  # ids survived the status change

    # A projected event is STILL replayable: a file on disk is not yet shared truth.
    assert [e.event_id for e in overlay.replayable_events(conn)] == ids
    assert overlay.is_dirty(conn) is True

    # Only pending and projected events are ever replayed. The other three are done:
    # committed reached the shared truth, discarded was withdrawn, conflicted was
    # refused — replaying any of them would apply the same intent twice.
    assert overlay.REPLAYABLE_STATUSES == (overlay.STATUS_PENDING, overlay.STATUS_PROJECTED)

    overlay.set_status(conn, [created.event_id], overlay.STATUS_COMMITTED)
    assert [e.event_id for e in overlay.replayable_events(conn)] == [moved.event_id]

    overlay.set_status(conn, [moved.event_id], overlay.STATUS_CONFLICTED)
    assert overlay.replayable_events(conn) == []
    assert overlay.is_dirty(conn) is False

    # A retired event is not deleted: the log keeps the audit trail, ids intact.
    archived = overlay.all_events(conn)
    assert [e.event_id for e in archived] == ids
    assert [e.status for e in archived] == [overlay.STATUS_COMMITTED, overlay.STATUS_CONFLICTED]
    assert all(e.projection_digest == result.digest for e in archived)

    # An unknown status is refused rather than silently written.
    with pytest.raises(ValueError, match="status"):
        overlay.set_status(conn, ids, "whatever")
