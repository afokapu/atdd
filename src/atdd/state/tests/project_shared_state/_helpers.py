# URN: component:project-shared-state:test-support:projection_helpers:backend:tests
# Runtime: python
# Purpose: Hermetic in-memory State Store fixtures shared by the project-shared-state acceptances.

"""Shared, hermetic fixtures for the project-shared-state acceptances (#1400).

Every unit acceptance in this wagon needs the same two things: an ephemeral,
migrated State Store that touches no developer SQLite, and a small logical store
of work items to project. Neither reaches the filesystem, the network, or a
provider — the projection spine is provider-free by construction, and these
helpers keep the tests that prove it provider-free too.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Tuple

from atdd.state.db import apply_migrations
from atdd.state.store import StateStore
from atdd.state.work_item_writer import mint_work_item, update_work_item


@contextmanager
def memory_store() -> Iterator[Tuple[sqlite3.Connection, StateStore]]:
    """An ephemeral, migrated State Store held entirely in RAM."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_migrations(conn)
    try:
        yield conn, StateStore(conn)
    finally:
        conn.close()


def two_work_items(conn: sqlite3.Connection) -> Tuple[str, str]:
    """Two work items with differing slugs, phases and wmbts. Returns their uids.

    Inserted in a deliberately non-sorted order (``zeta`` before ``alpha``, wmbts
    listed z-first) so a projection that leaked insertion order would be caught.
    """
    zeta = mint_work_item(
        conn, slug="zeta-feature", owner_actor="dev-b", title="Zeta", body="zeta body",
        phase="GREEN",
    )
    alpha = mint_work_item(
        conn, slug="alpha-feature", owner_actor="dev-a", title="Alpha", body="alpha body",
        phase="PLANNED",
    )
    update_work_item(conn, zeta.uid, {"wmbts": ["wmbt:w:E002", "wmbt:w:C001"], "train": "train:t:z"})
    update_work_item(conn, alpha.uid, {"wmbts": ["wmbt:w:E001"], "train": "train:t:a"})
    return zeta.uid, alpha.uid
