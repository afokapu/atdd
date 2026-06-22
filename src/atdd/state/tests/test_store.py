# URN: test:state-store:storage-apis:stores-and-projections
# Issue: #1182 (#1168 Phase 3)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1182 — typed storage APIs + read projections over the #1181 schema.

Covers ObjectStore (upsert/get/list/set_state/delete), RelationshipStore,
EventStore (monotonic seq + per-object listing), ExternalRefStore (link/resolve/
for_object), SyncStore (inbox/outbox lifecycle), the StateStore facade, and the
three core projections (work_item / run / evidence).
"""
from __future__ import annotations

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.projections import (
    evidence_projection,
    run_projection,
    work_item_projection,
)
from atdd.state.store import StateStore


@pytest.fixture()
def store(tmp_path):
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    conn = connect(db)
    try:
        yield StateStore(conn)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# ObjectStore
# --------------------------------------------------------------------------- #
def test_object_upsert_get_and_json_roundtrip(store):
    obj = store.objects.upsert("wi-1", "work_item", state="RED", data={"title": "x", "n": 3})
    assert obj.uid == "wi-1" and obj.state == "RED"
    got = store.objects.get("wi-1")
    assert got.data == {"title": "x", "n": 3}      # JSON round-trips as dict
    assert got.created_at and got.updated_at


def test_object_upsert_is_idempotent_update(store):
    store.objects.upsert("wi-1", "work_item", state="RED")
    store.objects.upsert("wi-1", "work_item", state="GREEN", data={"k": 1})
    assert len(store.objects.list(kind="work_item")) == 1
    assert store.objects.get("wi-1").state == "GREEN"


def test_object_set_state_and_missing_raises(store):
    store.objects.upsert("wi-1", "work_item", state="RED")
    store.objects.set_state("wi-1", "SMOKE")
    assert store.objects.get("wi-1").state == "SMOKE"
    with pytest.raises(KeyError):
        store.objects.set_state("nope", "X")


def test_object_list_filters_by_kind_and_delete(store):
    store.objects.upsert("wi-1", "work_item")
    store.objects.upsert("run-1", "run")
    assert {o.uid for o in store.objects.list(kind="work_item")} == {"wi-1"}
    assert len(store.objects.list()) == 2
    assert store.objects.delete("wi-1") is True
    assert store.objects.get("wi-1") is None
    assert store.objects.delete("wi-1") is False


# --------------------------------------------------------------------------- #
# RelationshipStore
# --------------------------------------------------------------------------- #
def test_relationship_add_list_remove_and_cascade(store):
    store.objects.upsert("parent", "work_item")
    store.objects.upsert("child", "work_item")
    store.relationships.add("parent", "child", "parent_of", data={"why": "decomposition"})
    assert [r.dst_uid for r in store.relationships.list(src_uid="parent")] == ["child"]
    assert store.relationships.list(rel_type="parent_of")[0].data == {"why": "decomposition"}
    # FK cascade: deleting the parent removes the edge
    store.objects.delete("parent")
    assert store.relationships.list() == []


# --------------------------------------------------------------------------- #
# EventStore
# --------------------------------------------------------------------------- #
def test_event_append_assigns_monotonic_seq(store):
    store.objects.upsert("run-1", "run")
    e1 = store.events.append("started", object_uid="run-1", payload={"phase": "RED"})
    e2 = store.events.append("advanced", object_uid="run-1")
    sys_event = store.events.append("system_tick")            # object_uid nullable
    assert [e1.seq, e2.seq, sys_event.seq] == [1, 2, 3]
    assert e1.payload == {"phase": "RED"}
    assert [e.event_type for e in store.events.list(object_uid="run-1")] == ["started", "advanced"]
    assert len(store.events.list()) == 3


# --------------------------------------------------------------------------- #
# ExternalRefStore
# --------------------------------------------------------------------------- #
def test_external_ref_link_resolve_and_for_object(store):
    store.objects.upsert("wi-1", "work_item")
    store.external_refs.link("wi-1", "github", "issue", "1182", data={"url": "…/1182"})
    ref = store.external_refs.resolve("github", "issue", "1182")
    assert ref.object_uid == "wi-1" and ref.data == {"url": "…/1182"}
    assert [r.ref_value for r in store.external_refs.for_object("wi-1")] == ["1182"]
    # re-link same provider/kind/value updates rather than duplicates
    store.external_refs.link("wi-1", "github", "issue", "1182", data={"url": "new"})
    assert store.external_refs.resolve("github", "issue", "1182").data == {"url": "new"}


# --------------------------------------------------------------------------- #
# SyncStore
# --------------------------------------------------------------------------- #
def test_sync_outbox_lifecycle(store):
    oid = store.sync.enqueue_outbox("github", "create_issue", {"title": "x"})
    pending = store.sync.pending_outbox()
    assert len(pending) == 1 and pending[0].operation == "create_issue"
    store.sync.mark_sent(oid)
    assert store.sync.pending_outbox() == []


def test_sync_inbox_lifecycle(store):
    iid = store.sync.enqueue_inbox("github", {"event": "issue.closed"})
    assert len(store.sync.pending_inbox()) == 1
    store.sync.mark_processed(iid)
    assert store.sync.pending_inbox() == []


# --------------------------------------------------------------------------- #
# Projections
# --------------------------------------------------------------------------- #
def test_work_item_projection_folds_external_refs(store):
    store.objects.upsert("wi-1", "work_item", state="RED", data={"title": "t"})
    store.external_refs.link("wi-1", "github", "issue", "1182")
    store.objects.upsert("run-1", "run")                      # excluded from work-item view
    rows = work_item_projection(store.conn)
    assert len(rows) == 1
    assert rows[0].uid == "wi-1" and rows[0].external == {"github": "1182"}


def test_run_projection_summarizes_events(store):
    store.objects.upsert("run-1", "run", state="active")
    store.events.append("started", object_uid="run-1")
    store.events.append("finished", object_uid="run-1")
    rows = run_projection(store.conn)
    assert len(rows) == 1
    assert rows[0].event_count == 2 and rows[0].last_event_type == "finished"


def test_evidence_projection_lists_evidence_only(store):
    store.objects.upsert("ev-1", "evidence", data={"kind": "validator-report"})
    store.objects.upsert("wi-1", "work_item")
    rows = evidence_projection(store.conn)
    assert [r.uid for r in rows] == ["ev-1"]
