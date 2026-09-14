# URN: test:migrate-projection-authority:migrate-store-projection:E002-UNIT-003-the-backup-survives-a-successful-migration
# Acceptance: acc:migrate-projection-authority:E002-UNIT-003-the-backup-survives-a-successful-migration
# WMBT: wmbt:migrate-projection-authority:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: After a SUCCESSFUL migration a backup still holds the pre-migration store and can be restored from — stated over the store's logical snapshot, because backup_store checkpoints the live WAL and the file's bytes move before the migration begins. Refs #2024.
"""The undo survives a successful migration (E002-UNIT-003).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:E002

``backup_store()`` returns the **sole** copied file. "Migrate against a `backup_store()` copy
and swap" therefore migrates the backup, and the operator is left with no undo at all — not
merely on a crash, but on **success**. The repo already ships the correct shape in
``reconcile``: an immutable ``backup_store`` *and* a separate mutable ``_scratch_copy``, swapped
with ``_replace_store``.

**Preservation is asserted over the snapshot, not the bytes**, and that is not a convenience.
``backup_store`` checkpoints the live store before copying it, so ``state.sqlite``'s bytes
change before any migration runs. A byte-identity assertion would fail a *correct*
implementation — it can only be made to pass by quiescing the store first, which is exactly the
kindness that would hide the defect. Refs #2024.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

from atdd.state import migrate_cli
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.reconcile import BACKUP_SUFFIX, _replace_store, backup_store
from atdd.state.manifest_migration import UNATTRIBUTED_OWNER
from atdd.state.store import StateStore

from ._helpers import control_root

#: Every table the store's content lives in. ``schema_migrations``/``sqlite_sequence`` are
#: excluded deliberately: they are bookkeeping, identical between any two stores at the same
#: schema version, and including them would make the comparison look stronger than it is.
SNAPSHOT_TABLES = (
    "objects", "relationships", "events", "external_refs",
    "overlay_events", "inbox", "outbox", "store_metadata",
)

def snapshot(db: Path) -> Dict[str, List[Tuple[Any, ...]]]:
    """The store's logical content: every row of every content table, order-independent."""
    conn = connect(db)
    try:
        return {
            table: sorted(tuple(row) for row in conn.execute(f"SELECT * FROM {table}"))
            for table in SNAPSHOT_TABLES
        }
    finally:
        conn.close()


def live_store(root: Path, count: int = 12):
    """A LIVE store: connection open, recent commits still in the write-ahead log.

    Deliberately not checkpointed. A fixture that quiesces the store first would make
    ``backup_store``'s own checkpoint a no-op and let a byte-identity claim pass that cannot
    hold in the real case.
    """
    db = init_state_store(start=Path(root))
    conn = connect(db)
    store = StateStore(conn)
    for index in range(count):
        store.objects.upsert(
            f"legacy-slug-{index}", WORK_ITEM_KIND, state="PLANNED",
            data={"title": f"item {index}"},
        )
    return db, conn


def run_migrate_store(root: Path, conn) -> int:
    """Drive the PRODUCTION verb — `atdd state migrate-store` — not a pattern of our own.

    A test that re-implements the intended design and asserts the design works proves nothing
    about the shipped code path. ``_cmd_migrate_store`` is what an operator runs, so it is what
    the acceptance drives.
    """
    conn.close()  # the CLI opens its own connection against the live store
    args = SimpleNamespace(
        op="migrate-store", root=str(root), dry_run=False,
        owner_actor=UNATTRIBUTED_OWNER, package=None,
    )
    return migrate_cli.dispatch(args)


def backups_beside(db: Path) -> List[Path]:
    """Every backup ``backup_store`` would have left next to the store."""
    return sorted(Path(db).parent.glob(f"{Path(db).name}{BACKUP_SUFFIX}*"))


def test_migrate_store_leaves_a_backup_holding_the_pre_run_snapshot(tmp_path: Path) -> None:
    """The property the one-copy design silently lost, asserted on the shipped verb.

    RED: ``_cmd_migrate_store`` opens the live store and mutates it in place. It calls
    ``backup_store`` zero times, so no backup exists at all — and the design this issue first
    specified would have migrated the backup itself, leaving none either way.
    """
    root = control_root(tmp_path / "root")
    db, conn = live_store(root)
    before = snapshot(db)

    assert run_migrate_store(root, conn) == 0, "the migration verb failed"

    backups = backups_beside(db)
    assert backups, (
        f"`atdd state migrate-store` left no backup beside {db}; the only surviving source of "
        "truth was mutated in place with no undo"
    )
    assert any(snapshot(backup) == before for backup in backups), (
        "a backup exists but none of them holds the pre-migration store — the migration wrote "
        "to the backup itself, so the operator has no undo even though the run succeeded"
    )


def test_migrate_store_really_did_migrate_the_live_store(tmp_path: Path) -> None:
    """The other half: preserving a backup must not mean skipping the migration."""
    root = control_root(tmp_path / "root")
    db, conn = live_store(root)
    before = snapshot(db)

    assert run_migrate_store(root, conn) == 0

    assert snapshot(db) != before, "the live store was not migrated at all"
    uids = [row["uid"] for row in connect(db).execute(
        "SELECT uid FROM objects WHERE kind=?", (WORK_ITEM_KIND,))]
    assert uids and all(uid.startswith("wi_") for uid in uids), (
        f"the live store still carries slug-shaped uids: {sorted(uids)[:3]}"
    )


def test_restoring_the_backup_returns_the_pre_run_store(tmp_path: Path) -> None:
    """A backup nobody can restore from is not an undo. Exercise the restore."""
    root = control_root(tmp_path / "root")
    db, conn = live_store(root)
    before = snapshot(db)

    assert run_migrate_store(root, conn) == 0
    backups = [b for b in backups_beside(db) if snapshot(b) == before]
    assert backups, "no restorable backup was left behind"

    with tempfile.TemporaryDirectory() as tmp:
        restored = Path(tmp) / "state.sqlite"
        shutil.copy2(backups[0], restored)
        _replace_store(restored, db)

    assert snapshot(db) == before, (
        "restoring the backup did not return the store to its pre-migration snapshot"
    )


def test_byte_identity_of_the_live_file_is_not_the_property(tmp_path: Path) -> None:
    """Pin the reason the acceptance is stated over the snapshot, so nobody re-tightens it.

    ``backup_store`` checkpoints the live store before copying, so ``state.sqlite``'s bytes
    change before any migration runs. This guards against a future revision "strengthening" the
    acceptance into something a correct implementation cannot satisfy.
    """
    db, conn = live_store(control_root(tmp_path / "root"))
    pre_run_bytes = Path(db).read_bytes()
    pre_run_snapshot = snapshot(db)

    backup = backup_store(db)

    assert Path(backup).read_bytes() != pre_run_bytes, (
        "this fixture quiesced the store before backing it up, which is exactly the kindness "
        "that hides the defect — the live file's bytes must still be in flux here"
    )
    assert snapshot(backup) == pre_run_snapshot, (
        "the backup's logical content diverged from the store it was taken from"
    )
    conn.close()
