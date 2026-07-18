# URN: component:reconcile-local-store:test-support:reconcile_helpers:backend:tests
# Runtime: python
# Purpose: Hermetic git-checkout + State Store fixtures shared by the reconcile-local-store acceptances.

"""Shared, hermetic fixtures for the reconcile-local-store acceptances (#1400).

Reconcile is defined *against a commit* — ``store == hydrate(projection @
store_base_commit) + replay(overlay)`` — so unlike the projection spine it cannot be
exercised in pure RAM: it needs a real repository with real commits. These helpers
build one under ``tmp_path``. It is still hermetic: a throwaway git repo, a throwaway
Control Root, a throwaway store, and **no provider and no network anywhere** — which
is precisely the property the wagon exists to prove (I7).
"""
from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import yaml

from atdd.state.db import connect, init_state_store
from atdd.state.projection import PROJECTION_RELATIVE

from .._fixtures import checkout as _checkout
from .._fixtures import (  # re-exported: the acceptances import these from this module
    commit_all,
    git,
    head,
)

#: Pinned identities, so a fixture's bytes never move between runs. 10 Crockford
#: Base32 time characters + 16 random ones, matching the contract's uid pattern.
UID_A = "wi_01HF7YAT00M78607F0000000A1"
UID_B = "wi_01HF7YAT00M78607F0000000B2"


def checkout(path: Path) -> Path:
    """A real git repo carrying a real Control Root marker, with one commit on it.

    ``initial_branch=None``: this wagon never names a branch, so git picks — as it always did.
    """
    return _checkout(path, initial_branch=None, extra_files={"README.md": "fixture\n"})


def document(
    uid: str,
    *,
    phase: str = "PLANNED",
    state: str = "ACTIVE",
    owner: str = "dev-a",
    slug: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """A valid ``commons:projection-object`` document."""
    doc: Dict[str, Any] = {
        "uid": uid,
        "phase": phase,
        "state": state,
        "owner_actor": owner,
        "slug": slug or uid.lower(),
    }
    doc.update(extra)
    return doc


def projection_dir(repo: Path) -> Path:
    return repo / PROJECTION_RELATIVE


def write_projection(repo: Path, documents: Iterable[Dict[str, Any]]) -> Path:
    """Write ``documents`` into the repo's committed-projection directory."""
    out = projection_dir(repo)
    out.mkdir(parents=True, exist_ok=True)
    for doc in documents:
        (out / f"{doc['uid']}.yaml").write_text(
            yaml.safe_dump(doc, sort_keys=True, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
    return out


def store(repo: Path) -> sqlite3.Connection:
    """Open (creating and migrating if needed) the repo's State Store."""
    return connect(init_state_store(start=repo))


def store_file(repo: Path) -> Path:
    from atdd.state.reconcile import store_path

    return store_path(repo)


def store_bytes(repo: Path) -> bytes:
    """The raw bytes of ``state.sqlite`` — for proving a refusal changed nothing."""
    return store_file(repo).read_bytes()
