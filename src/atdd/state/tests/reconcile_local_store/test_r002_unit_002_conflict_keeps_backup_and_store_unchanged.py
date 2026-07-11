# URN: test:reconcile-local-store:reconcile-store-state:R002-UNIT-002-conflict-keeps-backup-and-store-unchanged
# Acceptance: acc:reconcile-local-store:R002-UNIT-002-conflict-keeps-backup-and-store-unchanged
# WMBT: wmbt:reconcile-local-store:R002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: on conflict the backup file still exists after the command returns, state.sqlite is byte-identical to its pre-reconcile content (overlay_events included), and no re-projection is written. Refs #1400.
"""A conflict costs the developer nothing (R002-UNIT-002).

wagon: reconcile-local-store | feature: reconcile-store-state | phase: RED
WMBT: wmbt:reconcile-local-store:R002

The strongest form of "reconcile is not overwrite" (I5): a *failed* reconcile must be
indistinguishable, on disk, from one that never ran. Byte-identical — not "logically
equivalent", not "rolled back", byte-identical — because a developer who has just been
told their work conflicts needs to trust that nothing else happened to it.

The mechanism is structural rather than careful: the replay runs entirely on a copy,
and the live store is swapped in only on success. There is no half-applied state to
roll back because nothing was ever applied. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import authoring, overlay
from atdd.state.projection import read_projection
from atdd.state.reconcile import ReplayConflictError, hydrate_store, reconcile

from ._helpers import (
    UID_A,
    checkout,
    commit_all,
    document,
    projection_dir,
    store,
    store_bytes,
    write_projection,
)


def test_r002_unit_002_conflict_keeps_backup_and_store_unchanged(tmp_path) -> None:
    """The backup survives, the store is byte-identical, and no projection is written."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED", owner="dev-a")])
    commit_all(repo, "base projection")
    hydrate_store(repo)

    conn = store(repo)
    try:
        authoring.request_transition(conn, UID_A, "GREEN")
        overlay_before = overlay.all_events(conn)
    finally:
        conn.close()

    # The incoming projection conflicts with that overlay.
    write_projection(repo, [document(UID_A, phase="SMOKE", owner="dev-a")])
    commit_all(repo, "divergent incoming")

    before = store_bytes(repo)
    projection_before = read_projection(projection_dir(repo))
    projection_bytes_before = {
        path.name: path.read_bytes() for path in sorted(projection_dir(repo).glob("*.yaml"))
    }

    with pytest.raises(ReplayConflictError) as raised:
        reconcile(repo)
    backup = raised.value.report.backup_path

    # The backup file still exists after the command returns.
    assert backup is not None
    assert backup.exists()
    assert backup.read_bytes() == before

    # state.sqlite is byte-identical to its pre-reconcile content.
    assert store_bytes(repo) == before

    # ... overlay_events included: the developer's intent is entirely intact.
    conn = store(repo)
    try:
        assert overlay.all_events(conn) == overlay_before
        assert overlay.is_dirty(conn) is True
    finally:
        conn.close()

    # No re-projection is written to .atdd/state/projection/.
    assert read_projection(projection_dir(repo)) == projection_before
    assert {
        path.name: path.read_bytes() for path in sorted(projection_dir(repo).glob("*.yaml"))
    } == projection_bytes_before
