# URN: test:state-store:work-item-reader:store-backed-reads
# Issue: #1203 (#1168 Phase 4 cutover); #1270 Slice G (manifest mirror deleted)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1203 Phase 1 — store-backed work-item reader (shadow reads).

The State Store is the read source for `atdd issue` work-item state. These tests
prove the reader:

- reproduces the seeded work-item data (status/train/branch keyed by the GitHub
  issue number) — the GT-301 equivalence gate, now against the store directly;
- reads from the **store** (a store mutation is reflected without any file write);
- returns ``None`` for an issue that is not registered (an unregistered issue is
  valid and must not crash the lifecycle);
- tolerates a cold store with **no** ``.atdd/manifest.yaml`` and no seeding
  provider — reads are ``None``, not a crash (#1270 Slice G: the manifest mirror
  and its auto-import were deleted; a cold store self-seeds from registered sync
  providers only — see ``test_work_item_reader_cold_start_seed.py``).
"""
from __future__ import annotations

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.state.work_item_reader import WorkItemReader

# The canonical seed data — the shape the manifest used to carry, now written
# straight into the store (the mirror the reader used to auto-import is gone).
_SESSIONS = [
    {
        "slug": "state-store-authoritative",
        "issue_number": 1203,
        "type": "implementation",
        "status": "PLANNED",
        "train": "0002",
        "branch": "feat/state-store-authoritative-work-item-lifecycle",
        "feature": "feature:atdd:state-store",
        "wagon": "govern-lifecycle",
    },
    {
        "slug": "older-thing",
        "issue_number": 900,
        "type": "refactor",
        "status": "COMPLETE",
        "train": "0001",
        "branch": "fix/older",
    },
]


def _seed_store(db, sessions=None):
    """Write session dicts straight into the store (what import_manifest did).

    Upserts one ``work_item`` per session keyed by slug and links its GitHub
    issue external-ref — the store shape the reader queries.
    """
    db = init_state_store(db_path=db)
    conn = connect(db)
    try:
        store = StateStore(conn)
        for s in sessions if sessions is not None else _SESSIONS:
            data = {k: v for k, v in s.items() if k not in ("slug", "status", "issue_number")}
            data["issue_number"] = s["issue_number"]
            store.objects.upsert(s["slug"], WORK_ITEM_KIND, state=s["status"], data=data)
            store.external_refs.link(
                s["slug"], GITHUB_PROVIDER, "issue", str(s["issue_number"]),
                data={"source": "test-seed"},
            )
    finally:
        conn.close()
    return db


def _lookup(sessions, issue_number):
    for s in sessions:
        if s["issue_number"] == issue_number:
            return s["status"], s["train"], s["branch"]
    return None, None, None


@pytest.fixture()
def reader(tmp_path):
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    _seed_store(db)
    with WorkItemReader(control_root=tmp_path, db_path=db) as r:
        yield r


def test_status_train_branch_match_seed(reader):
    assert reader.status(1203) == "PLANNED"
    assert reader.train(1203) == "0002"
    assert reader.branch(1203) == "feat/state-store-authoritative-work-item-lifecycle"

    assert reader.status(900) == "COMPLETE"
    assert reader.train(900) == "0001"
    assert reader.branch(900) == "fix/older"


def test_store_reads_match_seed(reader):
    """GT-301: every registered issue reads back the data it was seeded with."""
    for s in _SESSIONS:
        n = s["issue_number"]
        expected = _lookup(_SESSIONS, n)
        got = (reader.status(n), reader.train(n), reader.branch(n))
        assert got == expected, f"issue #{n}: store {got} != seed {expected}"


def test_reads_from_store(reader, tmp_path):
    """A store mutation is visible to the reader without any file write."""
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    conn = connect(db)
    try:
        StateStore(conn).objects.set_state("state-store-authoritative", "RED")
    finally:
        conn.close()
    assert reader.status(1203) == "RED"


def test_unregistered_issue_returns_none(reader):
    assert reader.status(424242) is None
    assert reader.train(424242) is None
    assert reader.branch(424242) is None


def test_no_manifest_empty_store_zero_providers_yields_none(tmp_path):
    """No ``.atdd/manifest.yaml``, an empty store, and no registered provider:
    reads are ``None`` (a tolerated cold miss), not a crash (#1270 Slice G)."""
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    assert not (tmp_path / ".atdd" / "manifest.yaml").exists()
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    with WorkItemReader(control_root=tmp_path, db_path=db) as r:
        assert r.status(1203) is None
        assert r.train(1203) is None
        assert r.branch(1203) is None


# -- #1270 slice A: wagon reads for the graph-context migration ------------- #


def test_wagon_reads_from_store(reader):
    """wagon() returns the stored wagon; None when unrecorded or unregistered."""
    assert reader.wagon(1203) == "govern-lifecycle"
    assert reader.wagon(900) is None  # session carries no wagon
    assert reader.wagon(424242) is None  # unregistered issue


def test_issue_wagon_map_holds_only_wagoned_issues(reader):
    """issue_wagon_map() maps issue → wagon, skipping issues with no wagon."""
    assert reader.issue_wagon_map() == {1203: "govern-lifecycle"}


def test_issue_wagon_map_reads_from_store(reader, tmp_path):
    """A store-only wagon write is reflected immediately."""
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    conn = connect(db)
    try:
        store = StateStore(conn)
        obj = store.objects.get("older-thing")
        store.objects.upsert(
            "older-thing", obj.kind, state=obj.state,
            data={**obj.data, "wagon": "author-plan-substrate"},
        )
    finally:
        conn.close()
    assert reader.issue_wagon_map() == {
        1203: "govern-lifecycle",
        900: "author-plan-substrate",
    }
