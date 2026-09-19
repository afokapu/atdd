"""Prove the pre-migration backup is a faithful snapshot of the store (#2029).

``backup_store`` copies ``state.sqlite`` aside before the migration writes anything, and
until now nothing checked the copy. A backup nobody can prove is good is worth exactly as
much as no backup in the one situation you would ever reach for it — and the failure is
silent, because a truncated or half-written copy still opens.

**Why not byte equality.** ``backup_store`` runs ``PRAGMA wal_checkpoint(TRUNCATE)`` before
it copies, so the backup legitimately differs from the live file: pages move, the WAL is
folded in, free pages are released. Comparing bytes would fail on a *correct* backup. What
has to match is the **content** — the rows — so the comparison is a per-table checksum over
the rows themselves.

**Order-independence is deliberate.** The digest sorts its rows' hashes rather than reading
them in storage order. Today both sides are byte copies of one another and the order is the
same, so this costs a sort and buys nothing — but a backup that has been restored, vacuumed,
or round-tripped is the same store with a different page layout, and a check that called
that a corruption would be useless exactly when it was finally needed.

**What a mismatch means, and what it does not.** It means the backup is not a faithful
snapshot *of the store as it is now* — which is either a faulty copy or a write that landed
after the copy was taken. Either way the migration must not proceed, because the undo it
would retain does not describe the store it is about to change. But the two causes are **not
distinguished**, and this module does not pretend to: content alone cannot separate them.
A first draft tried, by re-reading the live store on the failure path and calling a moving
store "contention"; measured, a writer that commits once and stops reads as identical on both
reads and was reported as a corrupt backup. The heuristic was removed rather than shipped.
Telling them apart needs the reference read to be atomic with the copy — a read transaction
held across ``backup_store``'s checkpoint and copy — which changes that function's contract
and is not done here. :class:`BackupVerificationError` therefore names both causes and
accuses neither.

Dependency discipline: stdlib + ``atdd.state.store_contents`` for the statements. No SQL is
built here — table names cannot be bound as parameters and
``coder.security.sql-injection`` is strict, so the read statements are static text living
beside the replacement's, one entry per table.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List

from atdd.state.store_contents import _content_tables, statements_for

_log = logging.getLogger(__name__)

__all__ = [
    "BackupVerificationError",
    "snapshot_checksum",
    "store_snapshot_checksum",
    "verify_backup",
]


class BackupVerificationError(Exception):
    """The backup's contents do not match the store it was taken from.

    Deliberately does not attribute a cause. A faulty copy and a write that landed after the
    copy produce the same evidence, and both mean the retained undo does not describe the
    store about to be migrated — so both refuse, and the message says so rather than picking
    one. See the module docstring for why the two cannot be separated here.
    """

    def __init__(self, backup: Path, tables: List[str]) -> None:
        self.backup, self.tables = Path(backup), list(tables)
        super().__init__(
            f"the backup at {self.backup} is not a faithful snapshot of the store: "
            f"{len(self.tables)} table(s) differ ({', '.join(self.tables)}). Either the copy "
            "is faulty or the store was written after it was taken; in both cases the undo "
            "would not restore what is about to change. Nothing was migrated — retry when "
            "the store is idle, and keep the backup for inspection."
        )


def _encode(value: object) -> bytes:
    """One column value as unambiguous bytes.

    Type-tagged and length-prefixed so no two distinct rows can encode alike: without the
    prefix, ``("a", "bc")`` and ``("ab", "c")`` would hash the same.
    """
    if value is None:
        payload = b"\x00"
    elif isinstance(value, bool):  # before int — bool IS an int in Python
        payload = b"\x05" + (b"1" if value else b"0")
    elif isinstance(value, int):
        payload = b"\x01" + repr(value).encode("ascii")
    elif isinstance(value, float):
        payload = b"\x02" + repr(value).encode("ascii")
    elif isinstance(value, str):
        payload = b"\x03" + value.encode("utf-8")
    elif isinstance(value, bytes):
        payload = b"\x04" + value
    else:  # pragma: no cover - sqlite returns only the types above
        raise TypeError(f"unhashable column type from sqlite: {type(value).__name__}")
    return len(payload).to_bytes(8, "big") + payload


def _row_digest(row: Iterable[object]) -> bytes:
    digest = hashlib.sha256()
    for value in row:
        digest.update(_encode(value))
    return digest.digest()


def _table_checksum(conn: sqlite3.Connection, table: str) -> str:
    """A digest of every row in ``table``, independent of the order they are stored in.

    The row count is folded in as well as the digests, so a table cannot be made to match by
    losing a duplicate row.
    """
    rows = conn.execute(statements_for(table).rows)
    digests = sorted(_row_digest(row) for row in rows)
    checksum = hashlib.sha256()
    checksum.update(str(len(digests)).encode("ascii"))
    for digest in digests:
        checksum.update(digest)
    return checksum.hexdigest()


def snapshot_checksum(conn: sqlite3.Connection) -> Dict[str, str]:
    """``table -> checksum`` for every content table the connection's database carries.

    The table list is read from the database rather than declared, so a table that this
    module has no statement for raises rather than being quietly left out of the comparison
    — a checksum that skips a table would agree about data it never looked at.
    """
    # noqa: N+1 — the loop is over TABLES (nine, fixed by the schema), not over rows. Each
    # table is read in one statement, so the statement count is O(tables) and independent
    # of how much data the store holds.
    return {table: _table_checksum(conn, table) for table in _content_tables(conn)}


def _open_read_only(db_path: Path) -> sqlite3.Connection:
    """Open ``db_path`` strictly for reading.

    Verification must not write to what it verifies: :func:`atdd.state.db.connect` sets
    ``journal_mode = WAL``, which is a write, and a check that modifies the backup it is
    inspecting cannot honestly report on it.
    """
    return sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)


def store_snapshot_checksum(db_path: Path) -> Dict[str, str]:
    """``table -> checksum`` for a store on disk, read without writing to it."""
    conn = _open_read_only(db_path)
    try:
        return snapshot_checksum(conn)
    finally:
        conn.close()


def _differing(left: Dict[str, str], right: Dict[str, str]) -> List[str]:
    return sorted(
        table
        for table in left.keys() | right.keys()
        if left.get(table) != right.get(table)
    )


def verify_backup(db_path: Path, backup: Path) -> Dict[str, str]:
    """Prove ``backup`` holds the same rows as the store at ``db_path``; return its checksums.

    This is the clause #2029 asks for: a *logical* snapshot comparison, table-level checksums
    rather than byte equality, and non-vacuous — a backup with a single row altered differs in
    that row's table and is refused.

    Raises :class:`BackupVerificationError` naming the differing tables. Nothing on disk is
    touched — the backup is opened read-only, and so is the store.
    """
    live = store_snapshot_checksum(db_path)
    copy = store_snapshot_checksum(backup)
    differing = _differing(live, copy)
    if not differing:
        _log.info(
            "backup verified against the store by logical snapshot comparison",
            extra={"db_path": str(db_path), "backup": str(backup), "tables": len(copy)},
        )
        return copy

    _log.error(
        "the backup does not match the store it was taken from",
        extra={"db_path": str(db_path), "backup": str(backup), "tables": differing},
    )
    raise BackupVerificationError(backup, differing)
