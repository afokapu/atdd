# URN: test:project-shared-state:compute-projection-digest:E003-UNIT-001-digest-stable-and-change-sensitive
# Acceptance: acc:project-shared-state:E003-UNIT-001-digest-stable-and-change-sensitive
# WMBT: wmbt:project-shared-state:E003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The projection digest is identical for identical canonical bytes and moves when any byte moves — two projections of one store agree, a mutated phase does not. Refs #1433.
"""The digest is stable and change-sensitive (E003-UNIT-001).

wagon: project-shared-state | feature: compute-projection-digest | phase: RED
WMBT: wmbt:project-shared-state:E003

The digest is what a commit trailer pins (spec §5: ``ATDD-Projection-Digest``). A
digest that missed a change would let a projection drift under a trailer that still
claims to describe it. Refs #1433 / #1400.
"""
from __future__ import annotations

from atdd.state.projection import DIGEST_PREFIX, project, projection_digest
from atdd.state.work_item_writer import mint_work_item, update_work_item

from ._helpers import memory_store


def test_e003_unit_001_digest_stable_and_change_sensitive(tmp_path) -> None:
    """Two projections of one store share a digest; a mutated phase changes it."""
    with memory_store() as (conn, store):
        obj = mint_work_item(conn, slug="feature-x", owner_actor="dev-a", phase="PLANNED")

        project(store, tmp_path / "first")
        project(store, tmp_path / "second")

        # Mutate exactly one field — the phase — and project a third time.
        update_work_item(conn, obj.uid, {"phase": "RED"})
        project(store, tmp_path / "third")

    first = projection_digest(tmp_path / "first")
    second = projection_digest(tmp_path / "second")
    third = projection_digest(tmp_path / "third")

    # The first two digests are equal and carry the sha256: prefix.
    assert first == second
    assert first.startswith(DIGEST_PREFIX)
    assert len(first) == len(DIGEST_PREFIX) + 64

    # The third differs from the first two.
    assert third != first
