# URN: test:govern-lifecycle:state:E058-UNIT-002-set-version-reconciles-current-without-emitting-decision
# Acceptance: acc:govern-lifecycle:E058-UNIT-002-set-version-reconciles-current-without-emitting-decision
# WMBT: wmbt:govern-lifecycle:E058
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E058-UNIT-002 — set_version reconciles current but emits NO decision signal.

#1285 / #1172. The publish job reconciles the store's authoritative current from
the latest git tag (the store seed is stale, e.g. 3.149.0 vs the real 3.151.0).
That reconcile is NOT a decision to publish: ``set_version`` upserts the release
object and records a ``version_bumped`` audit event, but must enqueue no
``version_decided`` outbox message — only ``bump`` decides.
"""
from __future__ import annotations

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.projections import VERSION_BUMPED_EVENT, release_projection
from atdd.state.store import EventStore, StateStore
from atdd.state import version as ver


@pytest.fixture()
def conn(tmp_path):
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    c = connect(db)
    try:
        yield c
    finally:
        c.close()


def test_set_version_upserts_authoritative_current(conn):
    ver.set_version(conn, "3.151.0")
    assert ver.current(conn) == "3.151.0"


def test_set_version_records_reconcile_audit_event(conn):
    ver.set_version(conn, "3.151.0")
    events = EventStore(conn).list(object_uid=ver.RELEASE_UID)
    assert any(e.event_type == VERSION_BUMPED_EVENT for e in events)
    assert release_projection(conn).version == "3.151.0"


def test_set_version_emits_no_version_decided_signal(conn):
    """Reconciling current from an already-published tag is not a publish
    decision — the outbox stays empty (contrast ``bump``, which enqueues one)."""
    ver.set_version(conn, "3.151.0")
    assert StateStore(conn).sync.pending_outbox() == []
