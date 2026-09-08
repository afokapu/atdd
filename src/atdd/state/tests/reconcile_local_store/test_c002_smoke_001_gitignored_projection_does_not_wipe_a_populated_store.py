# URN: test:reconcile-local-store:guard-dirty-store:C002-SMOKE-001-gitignored-projection-does-not-wipe-a-populated-store
# Acceptance: acc:reconcile-local-store:C002-SMOKE-001-gitignored-projection-does-not-wipe-a-populated-store
# WMBT: wmbt:reconcile-local-store:C002
# Phase: RED
# Layer: smoke
# Runtime: python
# Assertion: behavioral
# Purpose: the 2026-07-20 incident, reproduced end to end — a gitignored (therefore absent) projection plus a HEAD move must NOT delete a populated store; reconcile refuses and every work_item survives. Refs #1580.
"""The incident itself, reproduced (C002-SMOKE-001).

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C002

On 2026-07-20 ~588 work_items were deleted from the shared store in a single operation.
The chain was short and every link was "working as designed":

1. ``.gitignore`` carried a bare ``.atdd/state/``, so ``.atdd/state/projection/`` — the
   *shared source of truth* — was never committed. Zero commits, zero files on disk.
2. The store model is ``store == hydrate(projection @ HEAD) + overlay``, so a gitignored
   projection is **empty at every HEAD**.
3. A git hook runs ``atdd state reconcile`` on every HEAD-moving operation.
4. ``_replace_public_state`` deleted every work_item *not in* the empty incoming projection.
5. The store was **clean**, so ``DirtyStoreError`` — the only guard that existed — never fired.

This test is that chain, run against a throwaway repo. It is the acceptance for "this class of
bug is closed": it fails on the code as it stood on 2026-07-21, and it must never fail again.

Nothing here touches a real store: a ``tmp_path`` checkout, a ``tmp_path`` Control Root, a
``tmp_path`` sqlite, and no provider anywhere. Refs #1580.
"""
from __future__ import annotations

import subprocess

import pytest

from atdd.state import metadata
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.reconcile import MassDeletionRefused, projection_path, reconcile
from atdd.state.store import StateStore

from ._helpers import checkout, commit_all, document, store, store_bytes

#: Enough objects that the loss would be unmistakable, and enough to trip any threshold.
_POPULATION = 40


def _uid(index: int) -> str:
    """A pinned, contract-shaped uid — 10 time chars + 16 random ones."""
    return f"wi_01HF7YAT00M78607F{index:09d}"


def _populate(repo, count: int) -> list:
    """Seed ``count`` clean work_items and anchor the store at HEAD.

    Written straight through the object store and stamped by hand: the incident store was
    **clean** (``overlay_events = 0``), and that is the whole reason the pre-existing guard
    stayed silent. A fixture that authored these through the overlay would be testing a
    different, already-guarded store.
    """
    conn = store(repo)
    try:
        state_store = StateStore(conn)
        uids = []
        for index in range(count):
            uid = _uid(index)
            document_for = document(uid, phase="GREEN")
            state_store.objects.upsert(
                uid,
                WORK_ITEM_KIND,
                state=document_for["phase"],
                data={k: v for k, v in document_for.items() if k not in ("uid", "phase")},
            )
            uids.append(uid)
        metadata.stamp_base_commit(conn, commit_all(repo, "anchor"))
        return uids
    finally:
        conn.close()


def test_c002_smoke_001_gitignored_projection_does_not_wipe_a_populated_store(tmp_path) -> None:
    """A HEAD move with an absent projection refuses; the populated store survives intact."""
    # 1. A checkout carrying the *incident's* .gitignore — the bare `.atdd/state/`.
    repo = checkout(tmp_path / "repo")
    (repo / ".gitignore").write_text(".atdd/state/\n", encoding="utf-8")
    commit_all(repo, "gitignore the whole state dir (the incident's mistake)")

    # The projection directory is genuinely unreachable by git: this is link 1 of the chain,
    # asserted rather than assumed, so the test fails loudly if the layout ever changes.
    ignored = subprocess.run(
        ["git", "check-ignore", "-v", str(projection_path(repo) / f"{_uid(0)}.yaml")],
        cwd=str(repo), capture_output=True, text=True, timeout=60,
    )
    assert ignored.returncode == 0, "fixture drift: the projection path is no longer gitignored"

    # 2. A populated, CLEAN store — 40 work_items, no overlay, anchored to a real commit.
    uids = _populate(repo, _POPULATION)
    assert not projection_path(repo).exists(), (
        "fixture drift: the incident's projection never existed on disk"
    )

    # 3. A HEAD-moving git operation — what the post-merge / post-checkout hook answers to.
    commit_all(repo, "a merge lands; HEAD moves")
    before = store_bytes(repo)

    # 4. Reconcile must REFUSE. On the code that caused the incident it instead deleted all 40.
    with pytest.raises(MassDeletionRefused) as refused:
        reconcile(repo)

    # The refusal is actionable: it names how many objects were at stake.
    message = str(refused.value)
    assert str(_POPULATION) in message, f"the refusal must name the count at stake: {message}"
    assert refused.value.existing == _POPULATION

    # 5. Nothing was lost, and nothing was even touched — state.sqlite is byte-identical.
    assert store_bytes(repo) == before, "a refusal must not mutate the store"

    conn = store(repo)
    try:
        survivors = {obj.uid for obj in StateStore(conn).objects.list(kind=WORK_ITEM_KIND)}
        assert survivors == set(uids), "every work_item must survive an absent projection"
        # The audit trail is intact precisely because nothing was deleted (events FK-cascade).
        assert conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0] >= _POPULATION
    finally:
        conn.close()
