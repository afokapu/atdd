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
from pathlib import Path
from typing import Iterator, Tuple

from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.state.work_item_writer import mint_work_item, update_work_item

from .._fixtures import memory_store  # re-exported: the acceptances import it from here


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


#: The golden fixture's uids. Literal, not minted: a golden file exists to pin the
#: canonical bytes, so its identities must be pinned too. Real objects mint theirs.
GOLDEN_UIDS = ("wi_01HF7YAT00M78607F000000001", "wi_01HF7YAT00M78607F000000002")

#: Where the committed golden projection lives.
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

#: The file recording the golden projection's digest.
GOLDEN_DIGEST_FILE = GOLDEN_DIR / "digest.txt"


def golden_store(conn: sqlite3.Connection) -> StateStore:
    """The fixture store the golden files pin — fully literal, so its bytes never move."""
    store = StateStore(conn)
    store.objects.upsert(
        GOLDEN_UIDS[0], WORK_ITEM_KIND, state="PLANNED",
        data={
            "slug": "golden-alpha", "title": "Golden Alpha", "body": "alpha body",
            "owner_actor": "dev-a", "state": "ACTIVE", "train": "train:commons:spine",
            "wmbts": ["wmbt:golden:C001", "wmbt:golden:E001"],
        },
    )
    store.objects.upsert(
        GOLDEN_UIDS[1], WORK_ITEM_KIND, state="RED",
        data={
            "slug": "golden-beta", "title": "Golden Beta", "body": "beta body",
            "owner_actor": "dev-b", "state": "ACTIVE", "train": None, "wmbts": [],
        },
    )
    return store
