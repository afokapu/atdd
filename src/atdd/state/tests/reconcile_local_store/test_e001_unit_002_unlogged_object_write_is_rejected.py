# URN: test:reconcile-local-store:record-overlay-events:E001-UNIT-002-unlogged-object-write-is-rejected
# Acceptance: acc:reconcile-local-store:E001-UNIT-002-unlogged-object-write-is-rejected
# WMBT: wmbt:reconcile-local-store:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: an object_store write that appends no overlay event raises OverlayLogError naming the uid, rolls the transaction back leaving object_store unchanged, and no overlay is derived by diffing SQLite against a hydrated baseline. Refs #1400.
"""Overlay is recorded, never inferred (E001-UNIT-002).

wagon: reconcile-local-store | feature: record-overlay-events | phase: RED
WMBT: wmbt:reconcile-local-store:E001

If a write could reach ``object_store`` without appending an event, reconcile would
have to *infer* what the developer meant by diffing SQLite — and the diff would carry
derived data, indexes and transient fields alongside the intent. So the write is
refused. A guard inside the authoring transaction aborts before the row is written,
which is what makes "every local authoring command appends an event" a property of
the store rather than a convention the caller is trusted to follow. Refs #1400.
"""
from __future__ import annotations

import sqlite3

import pytest

from atdd.state import authoring, overlay
from atdd.state.db import apply_migrations
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.overlay import OverlayLogError
from atdd.state.store import StateStore

_ROGUE = "wi_01HF7YAT00M78607F000000R09"


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    apply_migrations(connection)
    yield connection
    connection.close()


def test_e001_unit_002_unlogged_object_write_is_rejected(tmp_path, conn) -> None:
    """The unlogged write raises naming the uid, and object_store is left unchanged."""
    store = StateStore(conn)
    logged = authoring.create_object(conn, slug="feature-y", owner_actor="dev-b")
    before = [(o.uid, o.state, o.data) for o in store.objects.list(kind=WORK_ITEM_KIND)]
    events_before = overlay.all_events(conn)

    # A code path that mutates object_store directly, without going through the
    # overlay log, inside an authoring transaction.
    with pytest.raises(OverlayLogError) as refused:
        with overlay.authoring_session(conn):
            store.objects.upsert(_ROGUE, WORK_ITEM_KIND, state="INIT", data={"slug": "rogue"})

    # An OverlayLogError is raised identifying the unlogged object uid.
    assert refused.value.object_uid == _ROGUE
    assert _ROGUE in str(refused.value)

    # The transaction is rolled back and object_store is unchanged: the rogue object
    # never landed, and the object that WAS logged is untouched.
    assert store.objects.get(_ROGUE) is None
    assert [(o.uid, o.state, o.data) for o in store.objects.list(kind=WORK_ITEM_KIND)] == before
    assert overlay.all_events(conn) == events_before

    # Editing an existing object without logging is refused just the same — the guard
    # covers UPDATE, not only INSERT, so a phase could not be moved off the books.
    with pytest.raises(OverlayLogError) as edited:
        with overlay.authoring_session(conn):
            store.objects.upsert(
                logged.object_uid, WORK_ITEM_KIND, state="GREEN", data={"slug": "hijacked"},
            )
    assert edited.value.object_uid == logged.object_uid
    assert [(o.uid, o.state, o.data) for o in store.objects.list(kind=WORK_ITEM_KIND)] == before

    # No overlay is derived by diffing SQLite against a hydrated baseline: the log is
    # append-only from explicit authoring, and the module offers no diff/infer verb.
    assert not [name for name in dir(overlay) if "diff" in name or "infer" in name]

    # The sanctioned path still works — the guard rejects unlogged writes, not writes.
    ok = authoring.request_transition(conn, logged.object_uid, "PLANNED")
    assert ok.kind == overlay.PHASE_TRANSITION_REQUESTED
    assert store.objects.get(logged.object_uid).state == "PLANNED"
