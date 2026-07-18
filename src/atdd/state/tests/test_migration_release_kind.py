# URN: test:state-store:migrations:release-kind-v2
# Issue: #1172 (State Store owns version source-of-truth)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1172 — migration v2 (``release_kind``) registers the singleton release object.

Proves the v1→v2 upgrade applies cleanly, is idempotent, seeds exactly one
``release`` object (uid=``release``) at the authored baseline version, and reuses
the existing ``objects`` table (no new table is created by v2).
"""
from __future__ import annotations

import json

from atdd.state.db import apply_migrations, connect, current_version
from atdd.state.migrations import (
    CORE_MIGRATIONS,
    RELEASE_SEED_VERSION,
    latest_version,
)
from atdd.state.store import ObjectStore


def _tables(conn) -> set:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


#: v1 and v2 — the staged upgrade this module is about. Scoped explicitly rather than
#: taken as "everything", so a later migration (v3 overlay_events, #1400) extends the
#: schema without rewriting v2's own tests.
_UP_TO_V2 = [m for m in CORE_MIGRATIONS if m.version <= 2]


def test_release_kind_is_migration_v2():
    versions = [m.version for m in CORE_MIGRATIONS]
    assert versions == sorted(set(versions))     # ordered, append-only, no duplicates
    assert latest_version() >= 2
    v2 = next(m for m in CORE_MIGRATIONS if m.version == 2)
    assert v2.name == "release_kind"


def test_v2_applies_cleanly_over_v1(tmp_path):
    """Apply v1 first, then v2 — the staged upgrade must seed the release object."""
    conn = connect(tmp_path / "s.sqlite")
    try:
        # Stage 1: only v1.
        v1_only = [m for m in CORE_MIGRATIONS if m.version == 1]
        assert apply_migrations(conn, v1_only) == [1]
        assert current_version(conn) == 1
        assert ObjectStore(conn).get("release") is None  # not seeded yet

        # Stage 2: v2 applies on top.
        assert apply_migrations(conn, _UP_TO_V2) == [2]
        assert current_version(conn) == 2
        release = ObjectStore(conn).get("release")
        assert release is not None
        assert release.kind == "release"
        assert release.data == {"version": RELEASE_SEED_VERSION}
    finally:
        conn.close()


def test_v2_seed_present_after_full_apply(tmp_path):
    conn = connect(tmp_path / "s.sqlite")
    try:
        apply_migrations(conn)
        rows = conn.execute(
            "SELECT uid, kind, data FROM objects WHERE kind='release'"
        ).fetchall()
        assert len(rows) == 1                       # exactly one singleton
        assert rows[0]["uid"] == "release"
        assert json.loads(rows[0]["data"])["version"] == RELEASE_SEED_VERSION
    finally:
        conn.close()


def test_v2_reuses_objects_table_no_new_table(tmp_path):
    """v2 must NOT create a new table — the release kind rides the objects table."""
    conn = connect(tmp_path / "s.sqlite")
    try:
        apply_migrations(conn, [m for m in CORE_MIGRATIONS if m.version == 1])
        before = _tables(conn)
        apply_migrations(conn, _UP_TO_V2)
        after = _tables(conn)
        assert after == before                      # no schema-shape change in v2
    finally:
        conn.close()


def test_v2_is_idempotent_and_does_not_reseed(tmp_path):
    """Re-running must not duplicate the row nor clobber a bumped version."""
    conn = connect(tmp_path / "s.sqlite")
    try:
        apply_migrations(conn)
        # Simulate a later bump that changed the singleton's version.
        ObjectStore(conn).upsert("release", "release", data={"version": "9.9.9"})
        assert apply_migrations(conn) == []         # nothing pending
        # The ON CONFLICT DO NOTHING re-seed must not overwrite the bumped value.
        assert ObjectStore(conn).get("release").data == {"version": "9.9.9"}
        assert conn.execute(
            "SELECT COUNT(*) FROM objects WHERE uid='release'"
        ).fetchone()[0] == 1
    finally:
        conn.close()
