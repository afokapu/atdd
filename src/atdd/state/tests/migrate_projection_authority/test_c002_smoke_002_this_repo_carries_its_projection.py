# URN: test:migrate-projection-authority:migrate-store-projection:C002-SMOKE-002-this-repo-carries-its-projection
# Acceptance: acc:migrate-projection-authority:C002-SMOKE-002-this-repo-carries-its-projection
# WMBT: wmbt:migrate-projection-authority:C002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: The cutover has been performed on THIS repository — HEAD carries a committed projection byte-identical to one built from the live store. The only acceptance that separates a working mechanism from a performed migration. Refs #2029.
"""The cutover actually happened here (C002-SMOKE-002).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:C002

Every other C002 acceptance builds its own repo under ``tmp_path`` and proves the mechanism
works. None of them can fail when the mechanism works and the migration has simply never been
run — which is exactly the state #1622 was closed COMPLETE in, with two of its three Done-when
items unmet. This acceptance exists to be the one that notices.

**RED until the cutover runs.** It asserts against this repository's real HEAD and the live
Control Root store, so it fails while ``.atdd/state/projection`` is absent and passes once the
projection is committed. That is the point: it is the operator act's own test.

Byte-identity, not canonicality. ``check_canonicality`` asks only whether the committed
documents round-trip through themselves, so it passes just as happily on a stale or partial
commit. This compares the committed bytes against a projection of the store, uid for uid.

Read through git, never the working tree — ``gitstore.projection_bytes_at`` at HEAD (#2024).
A projection sitting un-committed on disk is not shared state.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.state import gitstore, projection as P
from atdd.state.db import connect
from atdd.state.paths import resolve_control_root
from atdd.state.store import StateStore

#: This repository's root, asked of git rather than counted off in ``parents[N]``.
#:
#: It was ``parents[4]`` and that is ``src/``, not the root — and the consequence was not a
#: noisy error. ``git ls-tree --name-only HEAD:.atdd/state/projection`` run from ``src/``
#: exits **0 with empty output**, so :func:`gitstore.projection_bytes_at` returned ``{}`` and
#: this test failed with "no projection committed at HEAD" whether or not one was committed.
#: Measured against a repository that really did carry a committed projection: from ``src/``
#: 0 documents, from the root 1. The acceptance that exists to prove the cutover happened
#: could not have gone green after a correct cutover. ``toplevel`` has no index to miscount.
_REPO = gitstore.toplevel(Path(__file__).resolve().parent)


def _live_store() -> Path:
    return resolve_control_root(_REPO).control_root / ".atdd" / "state" / "state.sqlite"


def test_the_repo_root_this_asserts_against_is_the_repo_root() -> None:
    """Guard the anchor, because a wrong one fails *quietly* and reads like a real verdict.

    ``git ls-tree HEAD:<dotted-path>`` from a subdirectory exits 0 with no output, so an
    anchor one level off turns this acceptance into a permanent red that nobody can
    distinguish from the red it is supposed to be. Assert the anchor separately, so the
    failure names the cause rather than the symptom.
    """
    assert (_REPO / ".git").exists(), f"{_REPO} is not a repository root"
    assert (_REPO / "src" / "atdd").is_dir(), (
        f"{_REPO} does not contain src/atdd — the anchor is not this repository's root"
    )


def test_c002_smoke_002_this_repo_carries_its_projection() -> None:
    """HEAD carries a projection, and it is the projection of the store."""
    prefix = P.PROJECTION_RELATIVE.as_posix()

    committed = gitstore.projection_bytes_at(_REPO, "HEAD", prefix)
    assert committed, (
        f"no projection committed at HEAD under {prefix} — the mechanism works "
        "(see the other C002 acceptances) but the cutover has not been performed on this "
        "repository. This is the gap #1622 closed COMPLETE over; #2029 exists to close it."
    )

    db = _live_store()
    if not db.exists() or db.stat().st_size == 0:
        pytest.skip(f"no live State Store at {db} — nothing to compare the projection against")

    conn = connect(db)
    try:
        expected = P.build_documents(StateStore(conn))
    finally:
        conn.close()

    expected_bytes = {
        f"{uid}{P.PROJECTION_SUFFIX}": P.canonical_bytes(doc)
        for uid, doc in expected.items()
    }
    committed_bytes = {k.rsplit("/", 1)[-1]: v for k, v in committed.items()}

    missing = sorted(set(expected_bytes) - set(committed_bytes))
    extra = sorted(set(committed_bytes) - set(expected_bytes))
    assert not missing and not extra, (
        f"the committed projection is not the projection of the store: "
        f"{len(missing)} uid(s) missing from HEAD, {len(extra)} stale at HEAD"
    )

    differing = sorted(k for k in expected_bytes if expected_bytes[k] != committed_bytes[k])
    assert not differing, (
        f"{len(differing)} document(s) differ between HEAD and the store, e.g. {differing[:3]}"
    )
