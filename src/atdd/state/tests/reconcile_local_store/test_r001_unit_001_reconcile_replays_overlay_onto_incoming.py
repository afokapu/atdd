# URN: test:reconcile-local-store:reconcile-store-state:R001-UNIT-001-reconcile-replays-overlay-onto-incoming
# Acceptance: acc:reconcile-local-store:R001-UNIT-001-reconcile-replays-overlay-onto-incoming
# WMBT: wmbt:reconcile-local-store:R001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: reconcile hydrates the incoming projection into public state, replays the overlay on top, re-projects the affected objects and advances store_base_commit B→H; a store with no overlay reduces to plain hydrate. Refs #1400.
"""store := hydrate(incoming) + replay(overlay) (R001-UNIT-001).

wagon: reconcile-local-store | feature: reconcile-store-state | phase: RED
WMBT: wmbt:reconcile-local-store:R001

This is invariant I3 made mechanical. The public half of the store is *replaced* by
the incoming projection — it is not merged, because the projection is the truth — and
the developer's private half is then replayed on top of it. Neither half is inferred:
the public half comes from committed YAML, the private half from the explicit event
log. The anchor advances only once the whole replay has succeeded. Refs #1400.
"""
from __future__ import annotations

from atdd.state import authoring, metadata, overlay
from atdd.state.projection import read_projection
from atdd.state.reconcile import hydrate_store, reconcile

from ._helpers import UID_A, UID_B, checkout, commit_all, document, projection_dir, store, write_projection


def test_r001_unit_001_reconcile_replays_overlay_onto_incoming(tmp_path) -> None:
    """The overlay replays onto the incoming projection; affected objects re-project."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED", owner="dev-a")])
    base = commit_all(repo, "base projection")
    hydrate_store(repo)

    # Private local authoring: a new object that exists nowhere but this store.
    conn = store(repo)
    try:
        created = authoring.create_object(conn, slug="feature-y", owner_actor="dev-b")
        local_uid = created.object_uid
        moved = authoring.request_transition(conn, local_uid, "PLANNED")
    finally:
        conn.close()

    # A peer's merged work arrives at H, touching disjoint objects: it advances UID_A
    # and adds UID_B. Neither is the local object.
    write_projection(
        repo,
        [document(UID_A, phase="GREEN", owner="dev-a"), document(UID_B, phase="RED", owner="dev-a")],
    )
    new_head = commit_all(repo, "peer merged work")

    result = reconcile(repo)

    # store_base_commit advances from B to H.
    assert result.mode == "replay"
    assert (result.base_commit, result.head) == (base, new_head)
    assert result.replayed == [created.event_id, moved.event_id]

    conn = store(repo)
    try:
        assert metadata.base_commit(conn) == new_head

        # The store equals hydrate(incoming_projection) ...
        rows = {
            row["uid"]: row["state"]
            for row in conn.execute("SELECT uid, state FROM objects WHERE kind='work_item'")
        }
        assert rows[UID_A] == "GREEN"   # the peer's advance is visible
        assert rows[UID_B] == "RED"     # the peer's new object arrived
        # ... with the overlay replayed on top: the private object survived intact.
        assert rows[local_uid] == "PLANNED"
    finally:
        conn.close()

    # Objects affected by the replay are re-projected — the local object now has a
    # projection file of its own, ready to be committed and shared.
    assert result.reprojected == [local_uid]
    projected = read_projection(projection_dir(repo))
    assert local_uid in projected
    assert projected[local_uid]["slug"] == "feature-y"
    assert projected[local_uid]["phase"] == "PLANNED"

    # A store with no overlay reduces to plain hydrate(incoming_projection).
    conn = store(repo)
    try:
        overlay.set_status(
            conn,
            [e.event_id for e in overlay.replayable_events(conn)],
            overlay.STATUS_COMMITTED,
        )
        assert overlay.is_dirty(conn) is False
    finally:
        conn.close()

    # The peer advances UID_A again, and UID_B goes missing from the projection with no
    # tombstone and no explanation.
    (projection_dir(repo) / f"{UID_B}.yaml").unlink()
    write_projection(repo, [document(UID_A, phase="SMOKE", owner="dev-a")])
    plain_head = commit_all(repo, "another peer commit")

    plain = reconcile(repo)
    assert plain.mode == "hydrate"
    assert plain.replayed == []
    assert plain.backup_path is None  # a clean store has nothing to lose, so no backup

    conn = store(repo)
    try:
        assert metadata.base_commit(conn) == plain_head
        rows = {
            row["uid"]: row["state"]
            for row in conn.execute("SELECT uid, state FROM objects WHERE kind='work_item'")
        }
        # Plain hydrate takes the projection's word for every object the projection
        # MENTIONS — UID_A moves to SMOKE. It does not take silence for a word: UID_B
        # vanished without a tombstone, which asserts nothing about UID_B, so UID_B stays
        # exactly as it was (#1580 — this used to delete it, and that is what emptied the
        # store on 2026-07-20). Retiring it requires saying so; see C002-UNIT-004.
        # The local object stays for the separate reason that it is private work with a
        # projection file of its own, still uncommitted.
        assert rows == {UID_A: "SMOKE", UID_B: "RED", local_uid: "PLANNED"}
    finally:
        conn.close()
