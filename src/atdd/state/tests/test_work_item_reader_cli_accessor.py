# URN: test:state-store:work-item-reader:cli-accessor
# Issue: #1320 (#1270 slice B — decommission the manifest mirror)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 slice B — WorkItemReader accessor extensions for the CLI readers.

Adds feature(), issue_number_for_slug(), session_entry() consumed by the
pr/branch/issue_lifecycle/sync_wmbts repoints. Isolated tmp-store tests
(explicit db_path), independent of the ambient control-root layout.
"""
from __future__ import annotations

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.state.work_item_reader import WorkItemReader

# #1270 Slice G: the manifest mirror was deleted — seed the store directly.
_SESSIONS = [
    {"slug": "state-store-authoritative", "issue_number": 1203,
     "type": "implementation", "status": "PLANNED", "train": "0002",
     "branch": "feat/ssa", "feature": "feature:atdd:state-store",
     "wagon": "govern-lifecycle", "created": "2026-06-01", "archived": None},
    {"slug": "older-thing", "issue_number": 900, "type": "refactor",
     "status": "COMPLETE", "train": "0001", "branch": "fix/older"},
]


@pytest.fixture()
def reader(tmp_path):
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    conn = connect(db)
    try:
        store = StateStore(conn)
        for s in _SESSIONS:
            data = {k: v for k, v in s.items() if k not in ("slug", "status")}
            store.objects.upsert(s["slug"], WORK_ITEM_KIND, state=s["status"], data=data)
            store.external_refs.link(
                s["slug"], GITHUB_PROVIDER, "issue", str(s["issue_number"]),
                data={"source": "test-seed"},
            )
    finally:
        conn.close()
    with WorkItemReader(control_root=tmp_path, db_path=db) as r:
        yield r


def test_feature_reads_from_store(reader):
    assert reader.feature(1203) == "feature:atdd:state-store"
    assert reader.feature(900) is None          # no feature recorded
    assert reader.feature(424242) is None        # unregistered


def test_issue_number_for_slug(reader):
    assert reader.issue_number_for_slug("state-store-authoritative") == 1203
    assert reader.issue_number_for_slug("older-thing") == 900
    assert reader.issue_number_for_slug("nope") is None


def test_session_entry_reconstructs_manifest_shape(reader):
    entry = reader.session_entry(1203)
    assert entry is not None
    assert entry["slug"] == "state-store-authoritative"   # from uid
    assert entry["status"] == "PLANNED"                    # from state
    assert entry["type"] == "implementation"               # from data
    assert entry["train"] == "0002"
    assert reader.session_entry(424242) is None
