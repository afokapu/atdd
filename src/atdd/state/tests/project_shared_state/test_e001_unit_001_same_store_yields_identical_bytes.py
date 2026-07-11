# URN: test:project-shared-state:project-store:E001-UNIT-001-same-store-yields-identical-bytes
# Acceptance: acc:project-shared-state:E001-UNIT-001-same-store-yields-identical-bytes
# WMBT: wmbt:project-shared-state:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: project(store) run twice over the same logical store yields byte-identical projection files, each named for its uid (invariant I1). Refs #1433.
"""project(store) is byte-identical for the same logical store (invariant I1).

wagon: project-shared-state | feature: project-store | phase: RED
WMBT: wmbt:project-shared-state:E001

Determinism is what makes the committed projection a *shared* source of truth: if
two runs over one logical store could differ, every peer would see spurious diffs
and CI could never take the round-trip identity as evidence. Refs #1433 / #1400.
"""
from __future__ import annotations

from atdd.state.projection import project

from ._helpers import memory_store, two_work_items


def test_e001_unit_001_same_store_yields_identical_bytes(tmp_path) -> None:
    """Two projections of one store into two directories are byte-for-byte equal."""
    with memory_store() as (conn, store):
        zeta_uid, alpha_uid = two_work_items(conn)

        first = project(store, tmp_path / "run-one")
        second = project(store, tmp_path / "run-two")

    # The set of emitted filenames is identical, and each is named for the
    # object's uid — never its slug.
    assert sorted(first.files) == sorted(second.files) == sorted([alpha_uid, zeta_uid])
    for uid, path in first.files.items():
        assert path.name == f"{uid}.yaml"

    # Every projection file is byte-identical between the two runs.
    for uid, path in first.files.items():
        assert path.read_bytes() == second.files[uid].read_bytes(), (
            f"projection of {uid} differs between two runs over the same logical store"
        )

    # The digest is taken over those canonical bytes, so it agrees too.
    assert first.digest == second.digest
