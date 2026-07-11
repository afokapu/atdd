# URN: test:reconcile-local-store:record-overlay-events:E001-UNIT-001-authoring-command-appends-overlay-event
# Acceptance: acc:reconcile-local-store:E001-UNIT-001-authoring-command-appends-overlay-event
# WMBT: wmbt:reconcile-local-store:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: each of the seven authoring commands appends exactly one ordered, typed, replayable overlay event in the same transaction as its object write; projecting the objects drains those events into `projected`. Refs #1400.
"""Every authoring command records its intent (E001-UNIT-001).

wagon: reconcile-local-store | feature: record-overlay-events | phase: RED
WMBT: wmbt:reconcile-local-store:E001

The correction this acceptance pins (spec §3): local overlay is **recorded, never
inferred**. SQLite holds derived data, indexes and transient fields, so diffing it
against a hydrated baseline recovers byte churn, not user intent. Instead each
authoring command appends one typed, replayable event — and it does so in the same
transaction as the object write, so the store and the log can never disagree about
what the developer did. Refs #1400.
"""
from __future__ import annotations

import sqlite3

import pytest

from atdd.state import authoring, overlay
from atdd.state.db import apply_migrations
from atdd.state.projection import STATE_TOMBSTONED, project
from atdd.state.store import StateStore


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    apply_migrations(connection)
    yield connection
    connection.close()


def test_e001_unit_001_authoring_command_appends_overlay_event(tmp_path, conn) -> None:
    """The seven commands each append exactly one typed event, in order; project drains them."""
    assert overlay.all_events(conn) == []

    # Invoke each of the seven authoring operations exactly once.
    created = authoring.create_object(conn, slug="feature-y", owner_actor="dev-b")
    uid = created.object_uid
    authoring.update_body(conn, uid, "the body")
    authoring.request_transition(conn, uid, "PLANNED")
    authoring.update_train(conn, uid, "train:commons:spine")
    authoring.add_wmbt(conn, uid, "wmbt:w:E001")
    authoring.apply_external_ref(conn, uid, "github", "1400")
    authoring.request_tombstone(conn, uid, "superseded")

    events = overlay.all_events(conn)

    # overlay_events gained one ordered, typed event per command.
    assert [e.kind for e in events] == [
        overlay.OBJECT_CREATED,
        overlay.BODY_UPDATED,
        overlay.PHASE_TRANSITION_REQUESTED,
        overlay.TRAIN_UPDATED,
        overlay.WMBT_ADDED,
        overlay.EXTERNAL_REF_APPLIED,
        overlay.TOMBSTONE_REQUESTED,
    ]
    assert [e.seq for e in events] == [1, 2, 3, 4, 5, 6, 7]
    assert {e.kind for e in events} == set(overlay.EVENT_KINDS)
    assert all(e.status == overlay.STATUS_PENDING for e in events)
    assert all(e.object_uid == uid for e in events)

    # Each event carries the payload a replay needs — not a diff, an intent.
    by_kind = {e.kind: e for e in events}
    assert by_kind[overlay.BODY_UPDATED].payload == {"body": "the body"}
    assert by_kind[overlay.PHASE_TRANSITION_REQUESTED].payload == {
        "from_phase": "INIT", "to_phase": "PLANNED",
    }
    assert by_kind[overlay.TRAIN_UPDATED].payload == {"train": "train:commons:spine"}
    assert by_kind[overlay.WMBT_ADDED].payload == {"wmbt": "wmbt:w:E001"}
    assert by_kind[overlay.EXTERNAL_REF_APPLIED].payload == {"provider": "github", "ref": "1400"}

    # The event and the object_store write landed together: the object carries every
    # command's effect, so neither half was committed without the other.
    obj = StateStore(conn).objects.get(uid)
    assert obj is not None
    assert obj.state == "PLANNED"
    assert obj.data["body"] == "the body"
    assert obj.data["train"] == "train:commons:spine"
    assert obj.data["wmbts"] == ["wmbt:w:E001"]
    assert obj.data["external_refs"] == {"github": "1400"}
    assert obj.data["state"] == STATE_TOMBSTONED

    # Committing the objects into projection drains the corresponding overlay events:
    # they leave `pending` and become `projected`, back-referenced to that projection.
    result = project(StateStore(conn), tmp_path / "projection")
    overlay.mark_projected(conn, result.digest)

    drained = overlay.all_events(conn)
    assert all(e.status == overlay.STATUS_PROJECTED for e in drained)
    assert all(e.projection_digest == result.digest for e in drained)
    assert [e.event_id for e in drained] == [e.event_id for e in events]  # ids are stable
