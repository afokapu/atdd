# URN: test:reconcile-local-store:track-base-commit:P001-UNIT-001-hydrate-stamps-base-commit
# Acceptance: acc:reconcile-local-store:P001-UNIT-001-hydrate-stamps-base-commit
# WMBT: wmbt:reconcile-local-store:P001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: hydrate() stamps store_base_commit == the commit it read the projection from, alongside the schema version and a clean dirty marker, and re-stamping the same commit is idempotent. Refs #1400.
"""hydrate anchors the store to a commit (P001-UNIT-001).

wagon: reconcile-local-store | feature: track-base-commit | phase: RED
WMBT: wmbt:reconcile-local-store:P001

The store is not free-floating. The relation the whole reconcile spine rests on
(I3) is ``store == hydrate(projection @ store_base_commit) + replay(overlay)``, and
``store_base_commit`` is the left-hand anchor. Without it, reconcile would have to
*guess* which projection the store's public half came from — and a wrong guess
replays local work onto the wrong public state. Refs #1400.
"""
from __future__ import annotations

from atdd.state import metadata
from atdd.state.migrations import latest_version
from atdd.state.reconcile import hydrate_store

from ._helpers import UID_A, checkout, commit_all, document, store, write_projection


def test_p001_unit_001_hydrate_stamps_base_commit(tmp_path) -> None:
    """The metadata holds store_base_commit == C, the schema version, and `clean`."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED")])
    commit = commit_all(repo, "projection at C")

    hydrated, stamped = hydrate_store(repo)
    assert hydrated == 1
    assert stamped == commit

    conn = store(repo)
    try:
        # store_base_commit == the commit the projection was read from.
        assert metadata.base_commit(conn) == commit

        # The metadata also carries the store schema version and a clean dirty marker.
        # Bound to the migration list rather than a literal: the claim is "hydrate
        # stamps *the* schema version", which a hard-coded number quietly turns into
        # "the schema is still v3" and breaks on every future migration.
        assert metadata.get(conn, metadata.SCHEMA_VERSION_KEY) == str(latest_version())
        assert metadata.get(conn, metadata.DIRTY_KEY) == metadata.DIRTY_CLEAN
        assert metadata.is_marked_dirty(conn) is False
    finally:
        conn.close()

    # Re-hydrating at the same commit is idempotent: it rewrites the same value.
    hydrated_again, stamped_again = hydrate_store(repo)
    assert (hydrated_again, stamped_again) == (1, commit)

    conn = store(repo)
    try:
        assert metadata.base_commit(conn) == commit
        assert metadata.get(conn, metadata.DIRTY_KEY) == metadata.DIRTY_CLEAN
    finally:
        conn.close()
