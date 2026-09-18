# URN: test:reconcile-local-store:guard-dirty-store:C001-UNIT-004-a-killed-migration-leaves-the-store-intact
# Acceptance: acc:reconcile-local-store:C001-UNIT-004-a-killed-migration-leaves-the-store-intact
# WMBT: wmbt:reconcile-local-store:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A migration killed part-way must leave the store intact and unmigrated rather than half-applied, and must need no operator cleanup. This is the failure mode the cure itself could introduce. Refs #2031.
"""A killed migration leaves the store intact (C001-UNIT-004).

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C001

The fix for the swap window changes *when* the store is mutated, so it can introduce a new
way to fail: a replacement applied part-way and then abandoned. That is worse than the defect
it cures — a half-migrated store cannot be told apart from an unmigrated one, the condition
:mod:`~atdd.state.store_migration`'s own docstring calls "no way back".

So it is pinned here as a guard on the cure, not a demonstration of the disease. The
previously specified Control-Root lockfile is what made it urgent: a lock whose holder dies
can wedge the store until somebody clears a file by hand. The requirement is that **no
hand-clearing is ever needed**, whatever the mechanism turns out to be.

Refs #2031.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from atdd.state.db import connect
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.state.store_contents import _content_tables

from ._helpers import checkout, store, store_file


def _legacy_store(repo: Path, count: int = 30) -> Path:
    conn = store(repo)
    try:
        objects = StateStore(conn).objects
        for index in range(count):
            objects.upsert(f"legacy-slug-{index}", WORK_ITEM_KIND, state="PLANNED",
                           data={"title": f"item {index}"})
    finally:
        conn.close()
    return store_file(repo)


def _snapshot(db: Path) -> dict:
    """The store's logical content — what "the store was preserved" has to mean.

    Not the file's bytes: the migration checkpoints the WAL before copying, so
    ``state.sqlite``'s bytes move before any content changes.
    """
    conn = connect(db)
    try:
        # Derived the way production derives it, never frozen here: a table added to the
        # schema is then covered by this comparison automatically. A hardcoded list would
        # read as "the store's content" while quietly omitting whatever was added — the
        # same claim-drifts-from-reality shape this work exists to prevent.
        return {
            table: sorted(tuple(row) for row in conn.execute(f"SELECT * FROM {table}"))
            for table in _content_tables(conn)
        }
    finally:
        conn.close()


def _killed_migration_source(db: Path) -> str:
    """Drive the real durable migration, then stop dead at the moment of replacement.

    Patching ``reconcile._replace_store`` leaves the process inside the production path with
    the replacement pending and nothing committed — the state a crash, a laptop sleep or a
    ``^C`` produces.
    """
    # Built with %-substitution, not a nested f-string: the child needs its own braces.
    return textwrap.dedent("""
        import sys, time
        sys.path.insert(0, %(root)r)
        import atdd.state.db as db_module
        from atdd.state.manifest_migration import UNATTRIBUTED_OWNER
        from atdd.state.store_migration import migrate_store_durably

        real_connect = db_module.connect

        class HangsOnCommit:
            \"\"\"Proxies a real connection, stopping dead at COMMIT.

            sqlite3.Connection is an immutable type, so the hang is installed by wrapping
            what db.connect returns. Every statement is the production one; only the final
            COMMIT never happens, which leaves the replacement transaction open with every
            row already rewritten — exactly a crash mid-apply.
            \"\"\"

            def __init__(self, inner):
                self._inner = inner

            def execute(self, sql, *args):
                if sql.strip().upper().startswith("COMMIT"):
                    print("AT-REPLACEMENT", flush=True)
                    time.sleep(300)
                return self._inner.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(self._inner, name)

        # Wrap ONLY the live store's connection. The working copy is migrated through
        # ObjectStore, which uses `with conn:` — and the context-manager protocol is looked
        # up on the type, so a proxy there would break the real code path rather than test it.
        def connect(path):
            inner = real_connect(path)
            return HangsOnCommit(inner) if str(path) == %(db)r else inner

        db_module.connect = connect
        migrate_store_durably(%(db)r, owner_actor=UNATTRIBUTED_OWNER)
    """) % {"root": str(Path(__file__).resolve().parents[4]), "db": str(db)}


@pytest.fixture()
def killed_mid_migration(tmp_path):
    """A store whose migration was SIGKILLed with the replacement pending."""
    repo = checkout(tmp_path / "repo")
    db = _legacy_store(repo)
    before = _snapshot(db)

    proc = subprocess.Popen(
        [sys.executable, "-c", _killed_migration_source(db)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    assert proc.stdout is not None, "the child was started without a stdout pipe"
    line = proc.stdout.readline().strip()
    if line != "AT-REPLACEMENT":
        proc.kill()
        raise AssertionError(
            f"the migration never reached the replacement: {line!r}\n"
            f"{proc.communicate()[1][-1500:]}"
        )
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait(timeout=60)
    time.sleep(0.3)
    return db, before


def test_the_store_reopens_and_passes_an_integrity_check(killed_mid_migration) -> None:
    """A killed migration must not leave a store nobody can open."""
    db, _before = killed_mid_migration
    conn = connect(db)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_its_content_equals_the_pre_migration_snapshot(killed_mid_migration) -> None:
    """Intact means unmigrated — not partially migrated.

    Stated over the snapshot, not the file's bytes: the migration checkpoints the WAL before
    copying, so a byte-identity assertion would fail a correct implementation.
    """
    db, before = killed_mid_migration
    assert _snapshot(db) == before, (
        "the store's content changed after the migration was killed — a half-applied "
        "replacement cannot be told apart from an unmigrated store"
    )


def test_no_object_is_half_migrated(killed_mid_migration) -> None:
    """The visible symptom: a mix of minted and slug-shaped uids."""
    db, _before = killed_mid_migration
    conn = connect(db)
    try:
        uids = sorted(row["uid"] for row in conn.execute(
            "SELECT uid FROM objects WHERE kind=?", (WORK_ITEM_KIND,)))
    finally:
        conn.close()
    minted = [uid for uid in uids if uid.startswith("wi_")]
    assert not minted, f"{len(minted)} of {len(uids)} objects were left migrated: {minted[:3]}"


def test_no_operator_cleanup_is_required(killed_mid_migration) -> None:
    """A second process must migrate straight away, with nothing cleared by hand.

    This is the requirement the lockfile design put at risk: a dead holder must not leave the
    store wedged behind a file somebody has to delete.
    """
    from atdd.state.manifest_migration import UNATTRIBUTED_OWNER
    from atdd.state.store_migration import migrate_store_durably

    db, before = killed_mid_migration
    result = migrate_store_durably(db, owner_actor=UNATTRIBUTED_OWNER)

    assert result.report.migrated, "the retry migrated nothing"
    assert _snapshot(db) != before, "the retry left the store unmigrated"
