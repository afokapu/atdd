# URN: test:reconcile-local-store:guard-dirty-store:C002-UNIT-004-absence-is-no-information-only-a-tombstone-retires
# Acceptance: acc:reconcile-local-store:C002-UNIT-004-absence-is-no-information-only-a-tombstone-retires
# WMBT: wmbt:reconcile-local-store:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: reconcile retains a work_item absent from the incoming projection instead of deleting it; only an explicit committed tombstone carrying actor, reason, source generation and prior digest retires one; a tombstone missing that provenance is refused; and a mass tombstone still trips the blast-radius guard. Refs #1580.
"""Absence is no information; only a tombstone retires (C002-UNIT-004).

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C002

This is the structural half of the fix, and the one that removes the incident's mechanism
rather than merely bounding its size.

The old rule read a *gap* as an instruction: an object the incoming projection did not carry
was deleted, because "hydrate replaces the public half, it does not merge into it". That
inference only holds while the projection at HEAD is known to be complete — and nothing
anywhere established that. A gitignored projection, a shallow clone, an older branch, a
Control Root resolved one directory off: each produces a projection that is missing objects
without asserting anything at all about them, and each was silently read as "delete these".

So absence now means what it actually means: **no information**. The object stays, untouched.

Retirement has to be *said*, and said with enough provenance to be audited afterwards — actor,
reason, the generation it was decided in, and the digest of the object as it stood before. A
tombstone carrying less than that is not a weaker claim, it is an unverifiable one, and it is
refused.

And because "somebody said it" is not the same as "somebody meant it at this scale", a
projection that retires an implausible share of the store in one reconcile still trips the
blast-radius guard from C002-UNIT-003. Refs #1580.
"""
from __future__ import annotations

import pytest

from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.projection import STATE_TOMBSTONED, ProjectionSchemaError
from atdd.state.reconcile import MassDeletionRefused, hydrate_store
from atdd.state.store import StateStore
from atdd.state.tombstone import tombstone_record

from ._helpers import UID_A, UID_B, checkout, commit_all, document, store, store_bytes, write_projection


def _uid(index: int) -> str:
    return f"wi_01HF7YAT00M78607F{index:09d}"


def _work_items(repo) -> dict:
    conn = store(repo)
    try:
        return {o.uid: o for o in StateStore(conn).objects.list(kind=WORK_ITEM_KIND)}
    finally:
        conn.close()


def test_c002_unit_004_absence_retains_the_object(tmp_path) -> None:
    """An object the incoming projection does not mention survives untouched."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED"), document(UID_B, phase="PLANNED")])
    commit_all(repo, "base projection")
    assert hydrate_store(repo)[0] == 2

    # UID_B vanishes from the projection — no tombstone, no statement of any kind. This is
    # the gap the old rule read as "delete it".
    (repo / ".atdd" / "state" / "projection" / f"{UID_B}.yaml").unlink()
    write_projection(repo, [document(UID_A, phase="GREEN")])
    commit_all(repo, "UID_B silently absent")

    hydrate_store(repo)

    items = _work_items(repo)
    # UID_A took the incoming update; UID_B is still here, and still says what it said.
    assert items[UID_A].state == "GREEN"
    assert UID_B in items, "absence from a projection must never delete an object"
    assert items[UID_B].state == "PLANNED"
    assert items[UID_B].data.get("state") != STATE_TOMBSTONED


def test_c002_unit_004_an_explicit_tombstone_retires(tmp_path) -> None:
    """A committed tombstone carrying full provenance does retire the object."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A), document(UID_B)])
    commit_all(repo, "base projection")
    hydrate_store(repo)

    retired = document(
        UID_B,
        state=STATE_TOMBSTONED,
        tombstone=tombstone_record(
            "superseded by #1580",
            actor="dev-a",
            source_generation="deadbeefcafe",
            prior_digest="sha256:" + "0" * 64,
        ),
    )
    write_projection(repo, [document(UID_A), retired])
    commit_all(repo, "UID_B explicitly retired")

    hydrate_store(repo)

    items = _work_items(repo)
    # The retirement is a RECORD: the object is still there, now carrying its tombstone and
    # the provenance that makes it auditable. Physical removal is compaction's job, not this.
    assert UID_B in items
    assert items[UID_B].data["state"] == STATE_TOMBSTONED
    tombstone = items[UID_B].data["tombstone"]
    assert tombstone["actor"] == "dev-a"
    assert tombstone["reason"] == "superseded by #1580"
    assert tombstone["source_generation"] == "deadbeefcafe"
    assert tombstone["prior_digest"].startswith("sha256:")
    assert tombstone["reason_digest"].startswith("sha256:")


def test_c002_unit_004_a_tombstone_without_provenance_is_refused(tmp_path) -> None:
    """Retirement that cannot be audited is refused, and nothing is applied."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A), document(UID_B)])
    commit_all(repo, "base projection")
    hydrate_store(repo)
    before = store_bytes(repo)

    # A bare "state: TOMBSTONED" with no actor, no reason, no generation, no prior digest —
    # a claim with nobody behind it.
    write_projection(
        repo, [document(UID_A), document(UID_B, state=STATE_TOMBSTONED, tombstone={})],
    )
    commit_all(repo, "an unattributable retirement")

    with pytest.raises(ProjectionSchemaError) as refused:
        hydrate_store(repo)

    message = str(refused.value)
    assert "actor" in message and "reason" in message, (
        f"the refusal must name the provenance it wanted: {message}"
    )
    assert store_bytes(repo) == before


def test_c002_unit_004_a_mass_tombstone_still_trips_the_blast_radius(tmp_path) -> None:
    """Saying it explicitly is not the same as meaning it at that scale."""
    repo = checkout(tmp_path / "repo")
    population = [document(_uid(i), phase="GREEN") for i in range(40)]
    write_projection(repo, population)
    commit_all(repo, "base projection")
    assert hydrate_store(repo)[0] == 40

    # 30 of 40 retired in one reconcile — each individually well-formed and fully attributed,
    # and collectively far past anything a single reconcile should do unattended.
    retirement = tombstone_record(
        "bulk retirement", actor="dev-a",
        source_generation="deadbeefcafe", prior_digest="sha256:" + "0" * 64,
    )
    mass = [
        document(_uid(i), phase="GREEN", state=STATE_TOMBSTONED, tombstone=retirement)
        if i < 30 else document(_uid(i), phase="GREEN")
        for i in range(40)
    ]
    write_projection(repo, mass)
    commit_all(repo, "bulk retirement")
    before = store_bytes(repo)

    with pytest.raises(MassDeletionRefused) as refused:
        hydrate_store(repo)
    assert "30" in str(refused.value)
    assert store_bytes(repo) == before

    # And it proceeds when the operator asserts the exact count they intend.
    hydrate_store(repo, allow_deletions=30)
    items = _work_items(repo)
    assert len(items) == 40, "retirement is a record; nothing is physically removed"
    assert sum(1 for o in items.values() if o.data.get("state") == STATE_TOMBSTONED) == 30
