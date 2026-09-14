# URN: test:migrate-projection-authority:migrate-store-projection:C003-UNIT-001-hydrate-preserves-stripped-keys
# Acceptance: acc:migrate-projection-authority:C003-UNIT-001-hydrate-preserves-stripped-keys
# WMBT: wmbt:migrate-projection-authority:C003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: hydrate over a POPULATED store preserves every STRIPPED_AT_PROJECTION key, because ObjectStore.upsert is a wholesale replace and the projection's silence about a field is not a claim that the field is empty. Measured: one cycle deletes 359 feature and 195 branch values. Refs #2025.
"""Silence is not an assertion of absence (C003-UNIT-001).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C003

This is the crux of #2025. `ObjectStore.upsert` is `data=excluded.data` — a wholesale
replace — and `hydrate` calls it once per projected object. `STRIPPED_AT_PROJECTION` omits
`branch`, `feature`, `worktree`, `created` and `id`, and those were authorized to be
stripped ONLY because the #1622 ruling established that "the store is never rebuilt from
the projection". Making hydrate a real inbound path removes that premise.

The moment it is real, the projector's SILENCE about a key becomes a DELETION of it.
Measured against the live corpus, one project+hydrate cycle takes the pre-commit
registration gate from 174/174 to 0/174 and the smoke-obligation gate likewise.

The fix is not to un-strip them — `branch` is per-machine and 49% of `feature`'s values are
the #2006 generator placeholder, so publishing them as authoritative shared state is the
harm, not the cure. The fix is that a wholesale replace was never the right semantics for an
inbound merge. A document that omits `branch` is not claiming the object has no branch; it
is declining to have an opinion.

RED: every stripped key is deleted from the store on the first hydrate.

NOTE ON THE HARNESS: this builds a POPULATED store and hydrates over it. `check_canonicality`
hydrates into an EMPTY MemoryStore, so it is structurally blind to this property and reports
canonical while the data is destroyed. An acceptance that leaned on it would pass vacuously.
"""
from __future__ import annotations

from atdd.state.projection import STRIPPED_AT_PROJECTION, hydrate, project
from atdd.state.work_item_writer import create_work_item

from ._helpers import memory_store

_LOCAL_ONLY = {
    "branch": "feat/some-real-branch",
    "feature": "feature:migrate-projection-authority:migrate-store-projection",
    "worktree": "feat-some-real-branch",
    "created": "2026-09-14",
    "id": 99001,
}


def test_an_inbound_ingest_deletes_no_locally_held_key(tmp_path) -> None:
    """Every STRIPPED_AT_PROJECTION value present before the hydrate is present after it."""
    with memory_store() as (conn, store):
        item = create_work_item(
            conn, "carries-local-state", state="PLANNED",
            data={"title": "carries local state", **_LOCAL_ONLY}, github_number=6001,
        )

        before = dict(store.objects.get(item.uid).data)
        assert all(key in before for key in _LOCAL_ONLY), "the given carries every stripped key"

        project(store, tmp_path / "projection")
        hydrate(tmp_path / "projection", store)

        after = dict(store.objects.get(item.uid).data)
        lost = {
            key: before[key] for key in STRIPPED_AT_PROJECTION
            if key in before and after.get(key) != before[key]
        }
        assert not lost, (
            "an inbound ingest deleted locally-held state the projection never spoke "
            f"about: {lost}. upsert is data=excluded.data, so the projector's silence "
            "about a stripped key reads as a deletion of it. The pre-commit registration "
            "gate reads data['branch'] and the smoke-obligation gate reads data['feature']; "
            "both go blind the moment this runs"
        )
