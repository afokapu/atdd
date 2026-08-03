# URN: test:state-store:db:schema-migrations-and-init
# Issue: #1181 (#1168 Phase 2)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1181 — State Store SQLite schema, migration runner, and `atdd state init`.

Covers the canonical pragmas, the core-table migration, idempotent re-runs,
version tracking, FK cascade (proving foreign_keys is ON), and that
``init_state_store`` creates ``state.sqlite`` with the full schema.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from atdd.state.db import (
    apply_migrations,
    connect,
    current_version,
    init_state_store,
)
from atdd.state.migrations import CORE_MIGRATIONS, latest_version

_SRC = Path(__file__).resolve().parents[3]

_CORE_TABLES = {
    "objects", "relationships", "events", "external_refs", "inbox", "outbox",
    # v3 (#1400 reconcile-local-store): the explicit overlay event log and the
    # store_base_commit metadata the reconcile spine is anchored on.
    "overlay_events", "store_metadata",
}

#: Every migration currently defined. Bump this when a migration is added.
_ALL_VERSIONS = [1, 2, 3]


def _table_names(conn) -> set:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


# --------------------------------------------------------------------------- #
# Migration runner
# --------------------------------------------------------------------------- #
def test_apply_migrations_creates_all_core_tables(tmp_path):
    conn = connect(tmp_path / "s.sqlite")
    try:
        applied = apply_migrations(conn)
        assert applied == _ALL_VERSIONS   # v1 core_tables, v2 release_kind, v3 overlay+metadata
        names = _table_names(conn)
        assert _CORE_TABLES.issubset(names)
        assert "schema_migrations" in names
        assert current_version(conn) == latest_version() == _ALL_VERSIONS[-1]
    finally:
        conn.close()


def test_apply_migrations_is_idempotent(tmp_path):
    conn = connect(tmp_path / "s.sqlite")
    try:
        assert apply_migrations(conn) == _ALL_VERSIONS
        assert apply_migrations(conn) == []          # nothing pending the second time
        # one bookkeeping row per applied migration
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        assert [r["version"] for r in rows] == _ALL_VERSIONS
    finally:
        conn.close()


def test_pragmas_applied_on_connect(tmp_path):
    conn = connect(tmp_path / "s.sqlite")
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_foreign_key_cascade_deletes_relationships(tmp_path):
    """Proves foreign_keys is enforced: deleting an object cascades to its rels."""
    conn = connect(tmp_path / "s.sqlite")
    try:
        apply_migrations(conn)
        with conn:
            conn.execute("INSERT INTO objects (uid, kind) VALUES ('a', 'work_item')")
            conn.execute("INSERT INTO objects (uid, kind) VALUES ('b', 'work_item')")
            conn.execute(
                "INSERT INTO relationships (src_uid, dst_uid, rel_type) VALUES ('a','b','parent_of')"
            )
        assert conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0] == 1
        with conn:
            conn.execute("DELETE FROM objects WHERE uid='a'")
        assert conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0] == 0
    finally:
        conn.close()


def test_objects_uid_unique_constraint(tmp_path):
    conn = connect(tmp_path / "s.sqlite")
    try:
        apply_migrations(conn)
        with conn:
            conn.execute("INSERT INTO objects (uid, kind) VALUES ('dup', 'work_item')")
        try:
            with conn:
                conn.execute("INSERT INTO objects (uid, kind) VALUES ('dup', 'run')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("duplicate uid should violate UNIQUE")
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# init_state_store (the prescribed #1168 test name)
# --------------------------------------------------------------------------- #
def test_state_init_creates_state_sqlite(tmp_path):
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    returned = init_state_store(db_path=db)
    assert returned == db
    assert db.is_file()
    conn = connect(db)
    try:
        assert _CORE_TABLES.issubset(_table_names(conn))
        assert current_version(conn) == latest_version()
    finally:
        conn.close()


def test_state_init_is_idempotent(tmp_path):
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    init_state_store(db_path=db)
    init_state_store(db_path=db)          # second run must not error or duplicate
    conn = connect(db)
    try:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        assert [r["version"] for r in rows] == _ALL_VERSIONS
    finally:
        conn.close()


def test_init_resolves_control_root_when_no_db_path(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".atdd").mkdir(parents=True)
    (repo / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")  # real Control Root
    (repo / ".git").mkdir()

    db = init_state_store(start=repo)
    assert db == repo / ".atdd" / "state" / "state.sqlite"
    assert db.is_file()


# --------------------------------------------------------------------------- #
# Live CLI smoke
# --------------------------------------------------------------------------- #
def test_state_init_cli_live(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".atdd").mkdir(parents=True)
    (repo / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")
    (repo / ".git").mkdir()

    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""),
           "HOME": str(repo), "CI": "true"}
    r = subprocess.run([sys.executable, "-m", "atdd", "state", "init", "--root", str(repo)],
                       cwd=str(repo), env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "initialized" in out
    assert f"Schema version: {_ALL_VERSIONS[-1]}" in out
    assert (repo / ".atdd" / "state" / "state.sqlite").is_file()
