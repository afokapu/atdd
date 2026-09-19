# URN: test:migrate-projection-authority:migrate-store-projection:C002-UNIT-005-the-backup-is-verified-by-logical-snapshot
# Acceptance: acc:migrate-projection-authority:C002-UNIT-005-the-backup-is-verified-by-logical-snapshot
# WMBT: wmbt:migrate-projection-authority:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The retained pre-migration backup must be PROVEN to hold the same rows as the store it was taken from — table-level checksum, not byte equality, and non-vacuous: a backup with one row altered is refused. Refs #2029.
"""The backup is verified by logical snapshot comparison (C002-UNIT-005).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C002

``backup_store()`` has always taken the copy, and #2024 wired it into the durable
migration, so a backup exists. Nothing ever checked it. A backup nobody can prove is good
fails silently and fails *late* — a truncated or half-written copy still opens, still looks
like a database, and is discovered to be worthless at the only moment it was ever needed.

**Why the comparison is logical and not byte-wise, asserted rather than asserted-about.**
``backup_store`` runs ``PRAGMA wal_checkpoint(TRUNCATE)`` before it copies, so a *correct*
backup differs in bytes from the pre-run file. ``test_byte_equality_would_refuse_a_good_backup``
measures that difference rather than taking it on trust — if it ever stops being true, the
justification for this whole design has changed and a test should say so.

**Non-vacuity is the point of this acceptance**, so the corruption cases are enumerated
rather than represented by one: altered row, deleted row, added row, and a single changed
byte inside one column. Two earlier Done-when in this program passed while proving nothing,
and both had the shape "assert the check ran".

Refs #2029.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Callable

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.manifest_migration import UNATTRIBUTED_OWNER
from atdd.state.reconcile import backup_store
from atdd.state.store import StateStore
from atdd.state.store_checksum import (
    BackupVerificationError,
    snapshot_checksum,
    store_snapshot_checksum,
    verify_backup,
)
from atdd.state.store_contents import UnknownStoreTableError
from atdd.state.store_migration import migrate_store_durably

#: The uid every corruption below reaches for. Literal, so the assertion knows it in advance.
VICTIM = "legacy-slug-7"


@pytest.fixture()
def store_with_pending_wal(tmp_path):
    """A file-backed store whose WAL still holds the writes, and an open connection.

    The connection is kept open deliberately: SQLite folds the WAL back in when the last
    connection closes, and a store that has quietly checkpointed itself cannot show the
    byte difference this acceptance rests on.
    """
    root = tmp_path / "repo"
    (root / ".atdd" / "state").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    db = init_state_store(start=root)
    held = connect(db)
    objects = StateStore(held).objects
    for index in range(40):
        objects.upsert(f"legacy-slug-{index}", WORK_ITEM_KIND, state="PLANNED",
                       data={"title": f"item {index}"})
    try:
        yield db, held
    finally:
        held.close()


def _corrupt(backup: Path, statement: str, *params: object) -> None:
    """Alter the BACKUP — never the store — with one plain sqlite3 write."""
    conn = sqlite3.connect(str(backup))
    try:
        conn.execute(statement, params)
        conn.commit()
    finally:
        conn.close()


def test_a_faithful_backup_verifies(store_with_pending_wal) -> None:
    """The other half of non-vacuity: a good backup must not be refused."""
    db, _held = store_with_pending_wal
    backup = backup_store(db)

    checksums = verify_backup(db, backup)

    assert checksums, "no table was checksummed"
    assert checksums == store_snapshot_checksum(db), (
        "verify_backup returned checksums that do not describe the store it just verified"
    )


def test_every_content_table_is_covered(store_with_pending_wal) -> None:
    """A checksum that skips a table agrees about data it never looked at.

    The table list is read from the store rather than declared here, so this cannot drift
    into checking eight of nine.
    """
    _db, held = store_with_pending_wal
    live = snapshot_checksum(held)

    in_store = {
        row[0]
        for row in held.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert set(live) == in_store, (
        f"tables in the store but not in the checksum: {sorted(in_store - set(live))}"
    )


def test_a_table_the_checker_cannot_read_refuses_rather_than_being_skipped(
    store_with_pending_wal,
) -> None:
    """A new table must stop the comparison, not quietly drop out of it."""
    db, held = store_with_pending_wal
    held.execute("CREATE TABLE side_car (uid TEXT PRIMARY KEY, note TEXT)")
    held.commit()

    with pytest.raises(UnknownStoreTableError) as caught:
        store_snapshot_checksum(db)

    assert "side_car" in str(caught.value)


@pytest.mark.parametrize(
    ("shape", "corrupt"),
    [
        ("one row altered", lambda b: _corrupt(
            b, "UPDATE objects SET state='GREEN' WHERE uid=?", VICTIM)),
        ("one row deleted", lambda b: _corrupt(
            b, "DELETE FROM objects WHERE uid=?", VICTIM)),
        ("one row added", lambda b: _corrupt(
            b, "INSERT INTO objects (uid, kind, state, data) VALUES (?,?,?,?)",
            "never-existed", WORK_ITEM_KIND, "PLANNED", "{}")),
        ("one byte inside one column", lambda b: _corrupt(
            b, "UPDATE objects SET data=replace(data,'item 7','item 8') WHERE uid=?", VICTIM)),
    ],
)
def test_a_corrupted_backup_is_refused(
    store_with_pending_wal, shape: str, corrupt: Callable[[Path], None],
) -> None:
    """THE bar this acceptance exists for, in each shape corruption actually takes."""
    db, _held = store_with_pending_wal
    backup = backup_store(db)
    corrupt(backup)

    with pytest.raises(BackupVerificationError) as caught:
        verify_backup(db, backup)

    assert caught.value.tables == ["objects"], (
        f"{shape}: the refusal named {caught.value.tables}, not the table that differs"
    )


def test_a_corruption_outside_objects_is_refused_and_named(store_with_pending_wal) -> None:
    """Coverage is not "the table the test happened to pick"."""
    db, _held = store_with_pending_wal
    backup = backup_store(db)
    _corrupt(backup, "DELETE FROM schema_migrations "
                     "WHERE version=(SELECT max(version) FROM schema_migrations)")

    with pytest.raises(BackupVerificationError) as caught:
        verify_backup(db, backup)

    assert caught.value.tables == ["schema_migrations"], caught.value.tables


def test_byte_equality_would_refuse_a_good_backup(store_with_pending_wal) -> None:
    """The measurement the logical comparison is justified by — not an assumption.

    ``backup_store`` checkpoints before it copies, so the pre-run file and a correct backup
    hold different bytes while holding identical rows. A byte-identity check would refuse
    this backup; the checksum accepts it.
    """
    db, _held = store_with_pending_wal
    wal = db.with_name(db.name + "-wal")
    assert wal.exists() and wal.stat().st_size > 0, (
        "the fixture did not leave writes in the WAL, so this measures nothing"
    )
    before = db.read_bytes()

    backup = backup_store(db)

    assert backup.read_bytes() != before, (
        "a correct backup no longer differs in bytes from the pre-run file — the reason "
        "this comparison is logical rather than byte-wise has changed"
    )
    assert verify_backup(db, backup), "the logical comparison refused a correct backup"


def test_verification_writes_to_neither_file(store_with_pending_wal) -> None:
    """A check that modifies what it inspects cannot honestly report on it."""
    db, _held = store_with_pending_wal
    backup = backup_store(db)
    before = backup.read_bytes()
    before_live = db.read_bytes()

    verify_backup(db, backup)

    assert backup.read_bytes() == before, "verification wrote to the backup"
    assert db.read_bytes() == before_live, "verification wrote to the store"


def test_the_durable_migration_refuses_when_the_backup_cannot_be_verified(
    tmp_path, monkeypatch,
) -> None:
    """End to end: an unverifiable undo stops the run, with the store untouched.

    The backup is corrupted through ``backup_store``'s own return value, so the failure is
    injected where a bad copy would really appear rather than by patching the check out.
    """
    root = tmp_path / "repo"
    (root / ".atdd" / "state").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    db = init_state_store(start=root)
    conn = connect(db)
    try:
        objects = StateStore(conn).objects
        for index in range(20):
            objects.upsert(f"legacy-slug-{index}", WORK_ITEM_KIND, state="PLANNED",
                           data={"title": f"item {index}"})
    finally:
        conn.close()

    from atdd.state import reconcile as reconcile_module

    real = reconcile_module.backup_store

    def damaged(path):
        backup = real(path)
        _corrupt(backup, "UPDATE objects SET state='GREEN' WHERE uid=?", VICTIM)
        return backup

    monkeypatch.setattr(reconcile_module, "backup_store", damaged)

    before = store_snapshot_checksum(db)
    with pytest.raises(BackupVerificationError):
        migrate_store_durably(db, owner_actor=UNATTRIBUTED_OWNER)

    assert store_snapshot_checksum(db) == before, (
        "the run refused but the store was changed anyway"
    )
    assert any(
        row[0].startswith("legacy-slug-")
        for row in connect(db).execute("SELECT uid FROM objects")
    ), "the store was migrated despite an unverifiable backup"


def test_the_migration_still_runs_when_the_backup_verifies(tmp_path) -> None:
    """Protecting the operator must not mean never migrating."""
    root = tmp_path / "repo"
    (root / ".atdd" / "state").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    db = init_state_store(start=root)
    conn = connect(db)
    try:
        objects = StateStore(conn).objects
        for index in range(20):
            objects.upsert(f"legacy-slug-{index}", WORK_ITEM_KIND, state="PLANNED",
                           data={"title": f"item {index}"})
    finally:
        conn.close()

    result = migrate_store_durably(db, owner_actor=UNATTRIBUTED_OWNER)

    assert result.report.migrated, "no work item was migrated"
    assert result.backup.exists(), "the verified backup was not retained"
    remaining = [
        row[0] for row in connect(db).execute("SELECT uid FROM objects")
        if row[0].startswith("legacy-slug-")
    ]
    assert not remaining, f"the store still carries slug-shaped uids: {remaining[:3]}"


def test_the_retained_backup_still_holds_the_pre_migration_store(tmp_path) -> None:
    """The backup is retained AND still restorable after a successful run."""
    root = tmp_path / "repo"
    (root / ".atdd" / "state").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    db = init_state_store(start=root)
    conn = connect(db)
    try:
        objects = StateStore(conn).objects
        for index in range(20):
            objects.upsert(f"legacy-slug-{index}", WORK_ITEM_KIND, state="PLANNED",
                           data={"title": f"item {index}"})
    finally:
        conn.close()
    before = store_snapshot_checksum(db)

    result = migrate_store_durably(db, owner_actor=UNATTRIBUTED_OWNER)

    assert store_snapshot_checksum(result.backup) == before, (
        "the retained backup no longer matches the pre-migration store"
    )
    assert store_snapshot_checksum(db) != before, "the store was not migrated at all"


def test_an_unreadable_backup_is_refused(store_with_pending_wal) -> None:
    """A truncated copy still looks like a file. It must not pass for a database."""
    db, _held = store_with_pending_wal
    backup = backup_store(db)
    backup.write_bytes(b"")

    with pytest.raises((BackupVerificationError, sqlite3.DatabaseError)):
        verify_backup(db, backup)


def test_a_missing_backup_is_refused(store_with_pending_wal, tmp_path) -> None:
    """The copy that was never written is the most complete corruption there is."""
    db, _held = store_with_pending_wal

    with pytest.raises(sqlite3.OperationalError):
        verify_backup(db, Path(tempfile.mkdtemp()) / "never-written.sqlite")
