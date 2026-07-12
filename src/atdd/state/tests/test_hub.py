# URN: test:state-store:hub-trace:projections-export-promote
# Issue: #1185 (#1168 Phase 6)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1185 — Hub trace alignment over the State Store.

Hub sessions/adapters/events are ordinary State Store primitives (object kinds +
relationships + events). Covers the recorders, the hub_session / hub_adapter
projections, export_trace (session + adapters + events), and the promotion
policy (enqueue to outbox + mark promoted), plus the `atdd state trace` CLI.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.state import hub
from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore

_SRC = Path(__file__).resolve().parents[3]


@pytest.fixture()
def store(tmp_path):
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    conn = connect(db)
    try:
        yield StateStore(conn)
    finally:
        conn.close()


def _seed(store):
    hub.record_session(store, "sess-1", state="active", data={"worker": "w1"})
    hub.record_adapter(store, "sess-1", "adapter-claude", data={"kind": "claude"})
    hub.record_adapter(store, "sess-1", "adapter-cmux", data={"kind": "cmux"})
    hub.record_event(store, "sess-1", "spawned", payload={"pid": 42})
    hub.record_event(store, "sess-1", "prompt_sent", payload={"text": "hi"})


# --------------------------------------------------------------------------- #
# Projections
# --------------------------------------------------------------------------- #
def test_hub_session_projection_includes_adapters_and_event_count(store):
    _seed(store)
    hub.record_session(store, "sess-2", state="idle")          # no adapters/events
    rows = {r.uid: r for r in hub.hub_session_projection(store)}
    assert set(rows) == {"sess-1", "sess-2"}
    assert rows["sess-1"].adapters == ["adapter-claude", "adapter-cmux"]
    assert rows["sess-1"].event_count == 2
    assert rows["sess-2"].adapters == [] and rows["sess-2"].event_count == 0


def test_hub_adapter_projection_links_back_to_session(store):
    _seed(store)
    rows = {r.uid: r for r in hub.hub_adapter_projection(store)}
    assert rows["adapter-claude"].session_uid == "sess-1"
    assert rows["adapter-cmux"].data == {"kind": "cmux"}


# --------------------------------------------------------------------------- #
# Trace export
# --------------------------------------------------------------------------- #
def test_export_trace_assembles_session_adapters_events(store):
    _seed(store)
    trace = hub.export_trace(store, "sess-1")
    assert trace["session"]["uid"] == "sess-1" and trace["session"]["data"]["worker"] == "w1"
    assert {a["uid"] for a in trace["adapters"]} == {"adapter-claude", "adapter-cmux"}
    assert [e["type"] for e in trace["events"]] == ["spawned", "prompt_sent"]
    assert trace["events"][0]["payload"] == {"pid": 42}


def test_export_trace_unknown_session_raises(store):
    with pytest.raises(KeyError):
        hub.export_trace(store, "nope")


def test_export_trace_rejects_non_session_object(store):
    store.objects.upsert("wi-1", "work_item")
    with pytest.raises(KeyError):
        hub.export_trace(store, "wi-1")


# --------------------------------------------------------------------------- #
# Promotion policy
# --------------------------------------------------------------------------- #
def test_promote_trace_enqueues_outbox_and_marks_promoted(store):
    _seed(store)
    outbox_id = hub.promote_trace(store, "sess-1")

    pending = store.sync.pending_outbox()
    assert len(pending) == 1
    assert pending[0].operation == hub.PROMOTE_OPERATION
    assert pending[0].payload["session"]["uid"] == "sess-1"     # the trace travels in the payload

    sess = store.objects.get("sess-1")
    assert sess.data["promoted"] is True and sess.data["promoted_outbox_id"] == outbox_id


def test_promote_trace_unknown_session_raises(store):
    with pytest.raises(KeyError):
        hub.promote_trace(store, "ghost")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_trace_cli_export_live(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".atdd").mkdir()
    (repo / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")

    # seed a session directly into the repo's store
    db = init_state_store(start=repo)
    conn = connect(db)
    try:
        _seed(StateStore(conn))
    finally:
        conn.close()

    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""),
           "HOME": str(repo), "CI": "true"}
    r = subprocess.run([sys.executable, "-m", "atdd", "state", "trace", "export",
                        "--session", "sess-1", "--root", str(repo)],
                       cwd=str(repo), env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["session"]["uid"] == "sess-1"
    assert len(doc["adapters"]) == 2 and len(doc["events"]) == 2
