# URN: test:drive-state-machine:record-agent-session-identity:M004-UNIT-002-recommit-updates-recency-not-created-at
# Acceptance: acc:drive-state-machine:M004-UNIT-002-recommit-updates-recency-not-created-at
# WMBT: wmbt:drive-state-machine:M004
# Phase: RED
# Harness: unit
# Layer: domain
"""M004-UNIT-002 — a re-committing session advances recency, keeps its created_at.

Issue #1540. Two things must both hold, and the easy implementations break one:
deleting-and-reinserting the ref refreshes recency but resets created_at; a
plain insert-if-absent preserves created_at but never refreshes recency.

Also asserts exactly ONE recency value is kept. #1540 explicitly refuses to
retain activity history — the store records that a session was seen, not a
timeline of every time it was.
"""
from __future__ import annotations

import pytest

from atdd.state.agent_session import REF_KIND_SESSION, AgentSession, record_participation

from ._agent_session_helpers import SLUG, control_root, open_store, seed_work_item

pytestmark = [pytest.mark.platform]

SESSION = AgentSession(provider="claude", session_id="6453e644-64cd-4254-add5-fa30135b52b1")


def _session_ref(store):
    refs = [r for r in store.external_refs.all() if r.ref_kind == REF_KIND_SESSION]
    assert len(refs) == 1, f"expected exactly one session ref, got {len(refs)}"
    return refs[0]


def _created_at(store, uid):
    row = store.conn.execute("SELECT created_at FROM external_refs WHERE object_uid=?", (uid,)).fetchone()
    return row[0]


def test_m004_unit_002_recommit_updates_recency_not_created_at(tmp_path):
    root = control_root(tmp_path)
    store = open_store(root)
    seed_work_item(store)

    record_participation(store, SLUG, SESSION, worktree_path="/wt", now="2026-07-18T01:00:00Z")
    store.conn.commit()

    first = _session_ref(store)
    first_created = _created_at(store, first.object_uid)
    assert first.data.get("last_seen_at") == "2026-07-18T01:00:00Z"

    # the same session commits again, hours later
    record_participation(store, SLUG, SESSION, worktree_path="/wt", now="2026-07-18T07:30:00Z")
    store.conn.commit()

    second = _session_ref(store)
    assert second.data.get("last_seen_at") == "2026-07-18T07:30:00Z", "recency must advance"
    assert _created_at(store, second.object_uid) == first_created, (
        "created_at is the session's identity anchor and must not be reset by a re-commit"
    )

    # exactly one recency value — no history accumulates
    blob = second.data or {}
    history_keys = [k for k in blob if k not in {"last_seen_at", "worktree_path"}]
    assert history_keys == [], f"no activity history may accumulate, found {history_keys}"
    assert not isinstance(blob.get("last_seen_at"), list)
