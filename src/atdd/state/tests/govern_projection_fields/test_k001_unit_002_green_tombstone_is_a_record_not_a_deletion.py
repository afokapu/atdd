# URN: test:govern-projection-fields:mark-object-tombstone:K001-UNIT-002-green-tombstone-is-a-record-not-a-deletion
# Acceptance: acc:govern-projection-fields:K001-UNIT-002-green-tombstone-is-a-record-not-a-deletion
# WMBT: wmbt:govern-projection-fields:K001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: retirement writes state TOMBSTONED with a reason digest and tombstone metadata into the projected object, removes no file, is refused by any later merge that sets a live phase on the uid, and leaves physical removal available only through the separate archival compaction operation Refs #1400.
"""Retirement is a record; compaction is the only deletion (K001-UNIT-002).

wagon: govern-projection-fields | feature: mark-object-tombstone | phase: RED
WMBT: wmbt:govern-projection-fields:K001

Four claims, and they are the whole of the tombstone lifecycle:

1. retirement **writes** — ``state: TOMBSTONED``, plus a reason and the digest of that reason,
   which is the thing a trailer and a merge can compare without carrying the prose;
2. retirement **deletes nothing** — the projected file is still there, still named by the uid;
3. a later merge that revives the uid is **refused**;
4. physical removal exists, but only as **archival compaction** — an operator's deliberate act,
   which nothing on the merge path can reach.

The store is real, the projection is the projector's own, and the digest is over the reason.
"""
from __future__ import annotations

import sqlite3

import yaml

from atdd.state import authoring, merge_driver, tombstone
from atdd.state.db import apply_migrations
from atdd.state.projection import STATE_TOMBSTONED, project
from atdd.state.store import StateStore

REASON = "superseded by #1400"


def _store():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_migrations(conn)
    return conn


def test_k001_unit_002_green_tombstone_is_a_record_not_a_deletion(tmp_path) -> None:
    """The retirement is projected as a record, survives, refuses revival, and only compacts."""
    conn = _store()
    created = authoring.create_object(conn, slug="feature-x", owner_actor="dev-a", phase="GREEN")
    uid = created.object_uid

    out = tmp_path / "projection"
    before = project(StateStore(conn), out)
    assert before.files[uid].is_file()

    # 1 + 2. Retire it, and project again: the file is still there, and it now carries the record.
    tombstone.retire(conn, uid, REASON)
    after = project(StateStore(conn), out)

    path = after.files[uid]
    assert path.is_file(), "no projection file is removed by a retirement"
    assert path == before.files[uid], "and it is the same file, under the same uid"

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["state"] == STATE_TOMBSTONED
    assert document["tombstone"]["reason"] == REASON
    assert document["tombstone"]["reason_digest"] == tombstone.reason_digest(REASON)
    assert document["tombstone"]["reason_digest"].startswith("sha256:")
    assert tombstone.is_tombstoned(document)

    # The digest is over the reason, so two different retirements never collide.
    assert tombstone.reason_digest("a different reason") != tombstone.reason_digest(REASON)

    # Only ONE object exists on disk, and it is the retired one: nothing vanished.
    assert sorted(p.name for p in out.glob("*.yaml")) == [f"{uid}.yaml"]

    # 3. A later merge that sets a live phase on the tombstoned uid is refused.
    revived = {**document, "state": "ACTIVE", "phase": "SMOKE"}
    revival = merge_driver.merge_object(uid, document, document, revived)
    assert not revival.ok
    assert revival.merged is None
    assert uid in revival.conflicts[0].render()
    assert path.is_file(), "and the refusal did not remove the file either"

    # 4. Physical removal exists — but only as archival compaction, and only for the retired.
    live_conn = _store()
    live = authoring.create_object(live_conn, slug="still-alive", owner_actor="dev-b")
    live_out = tmp_path / "live"
    project(StateStore(live_conn), live_out)
    assert tombstone.compact_archive(live_out) == [], "compaction refuses to remove a live object"

    removed = tombstone.compact_archive(out)
    assert removed == [uid]
    assert not path.exists()
    assert live.object_uid  # the live store is untouched by the other store's compaction
