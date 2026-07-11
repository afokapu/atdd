# URN: test:reconcile-local-store:hydrate-cold-store:P002-UNIT-002-holds
# Acceptance: acc:reconcile-local-store:P002-UNIT-002-holds
# WMBT: wmbt:reconcile-local-store:P002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: cold-start-hydrate succeeds when there is no store at all, or a store with no base commit, so long as no overlay is present — the projection alone rebuilds the store and stamps its anchor. Refs #1400.
"""Cold start needs nothing but the committed projection (P002-UNIT-002).

wagon: reconcile-local-store | feature: hydrate-cold-store | phase: RED
WMBT: wmbt:reconcile-local-store:P002

A fresh clone has no ``state.sqlite`` and no ``store_base_commit`` — only the committed
projection. That is the whole promise of the model: the shared truth is in git, so a new
developer (or CI, which has no store *by design*) rebuilds everything from the checkout
alone. No provider, no API, no store handed around out of band.

The reverse also holds, and is the point of the P002 pair: cold start is available
exactly when there is nothing to lose. Refs #1400.
"""
from __future__ import annotations

from atdd.state import metadata, overlay
from atdd.state.reconcile import hydrate_store, store_path

from ._helpers import UID_A, UID_B, checkout, commit_all, document, store, write_projection


def test_p002_unit_002_holds(tmp_path) -> None:
    """No store and no base commit still hydrates — from the projection alone."""
    repo = checkout(tmp_path / "repo")
    write_projection(
        repo,
        [document(UID_A, phase="PLANNED", owner="dev-a"), document(UID_B, phase="RED", owner="dev-b")],
    )
    commit = commit_all(repo, "projection")

    # The true cold start: no store file exists at all.
    assert not store_path(repo).exists()

    hydrated, base = hydrate_store(repo)

    # The projection alone rebuilt the store, and anchored it.
    assert hydrated == 2
    assert base == commit
    assert store_path(repo).exists()

    conn = store(repo)
    try:
        rows = {
            row["uid"]: row["state"]
            for row in conn.execute("SELECT uid, state FROM objects WHERE kind='work_item'")
        }
        assert rows == {UID_A: "PLANNED", UID_B: "RED"}
        assert metadata.base_commit(conn) == commit
        assert metadata.get(conn, metadata.DIRTY_KEY) == metadata.DIRTY_CLEAN

        # No overlay: a cold-started store has authored nothing, so it owes nothing.
        assert overlay.all_events(conn) == []
        assert overlay.is_dirty(conn) is False
    finally:
        conn.close()

    # The other cold-start shape: a store that EXISTS but was never anchored, and is
    # clean. There is nothing to lose, so hydrate proceeds and stamps it.
    conn = store(repo)
    try:
        metadata.set(conn, metadata.BASE_COMMIT_KEY, None)
        assert metadata.base_commit(conn) is None
    finally:
        conn.close()

    hydrated_again, base_again = hydrate_store(repo)
    assert (hydrated_again, base_again) == (2, commit)

    conn = store(repo)
    try:
        assert metadata.base_commit(conn) == commit
    finally:
        conn.close()
