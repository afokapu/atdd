# URN: test:migrate-projection-authority:migrate-store-projection:C003-UNIT-003-restore-preserves-ref-data
# Acceptance: acc:migrate-projection-authority:C003-UNIT-003-restore-preserves-ref-data
# WMBT: wmbt:migrate-projection-authority:C003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: restoring a ref must not wipe the row's existing data blob — ExternalRefStore.link is ON CONFLICT DO UPDATE SET data=excluded.data and _dumps(None) is '{}', which is the same wholesale-replace fault one table over. 1,103 live rows carry a blob. Refs #2025.
"""The restore must not wipe the row it restores (C003-UNIT-003).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C003

The obvious implementation of "restore the refs table" is
`store.external_refs.link(uid, "github", "issue", value)`. It is wrong, and wrong in
exactly the way this issue exists to correct.

`link` is `ON CONFLICT(provider, ref_kind, ref_value) DO UPDATE SET data=excluded.data`,
and `_dumps(None)` is `'{}'`. So restoring a ref that already exists REPLACES its `data`
blob with an empty object. 1,103 live `(github, issue)` rows carry a non-empty blob —
`{"source": "atdd-author"}`, `{"source": "branch-self-heal"}`, and the `_recovery`
provenance from the 2026-07-20 incident.

The projection does not carry that blob and has no opinion about it (carrying it would
readmit `_recovery`, which #1622 ruled DROP). Having no opinion is precisely why the restore
must not overwrite it.

RED, AND WHY IT TAKES TWO OBJECTS. The blob assertion ALONE passes today — vacuously,
because `hydrate` never touches the refs table at all, so there is nothing to wipe. A test
that only asserted blob survival would be green now, green after a correct fix, and green
after the naive `link(..., data=None)` fix too, right up until someone noticed 1,103 rows
had lost their provenance in production.

So the acceptance pins both halves of the same behaviour, with two objects:

  - one whose ref row is ABSENT from the table — hydrate must restore it (fails today,
    because hydrate restores nothing);
  - one whose ref row is PRESENT with a blob — hydrate must leave the blob alone (fails
    against the naive restore).

Only an implementation that manages the table AND merges into it satisfies both.
"""
from __future__ import annotations

from atdd.state.projection import hydrate, project
from atdd.state.work_item_writer import create_work_item

from ._helpers import memory_store

_GITHUB, _ISSUE = "github", "issue"
_PROVENANCE = {"source": "atdd-author", "confidence": "high"}


def test_the_restore_rebuilds_a_missing_ref_without_wiping_a_present_one(tmp_path) -> None:
    """hydrate manages the refs table AND merges into it: restores the absent, preserves the present."""
    with memory_store() as (conn, store):
        keeps_blob = create_work_item(
            conn, "ref-with-provenance", state="PLANNED",
            data={"title": "ref with provenance"}, github_number=8001,
        )
        needs_restore = create_work_item(
            conn, "ref-to-restore", state="PLANNED",
            data={"title": "ref to restore"}, github_number=8002,
        )
        # The shape 1,103 live rows carry.
        store.external_refs.link(keeps_blob.uid, _GITHUB, _ISSUE, "8001", data=dict(_PROVENANCE))

        project(store, tmp_path / "projection")

        # The inbound case: this peer's store never held 8002's ref. Deleting the row is how
        # a fresh or partial store arrives, and it is what hydrate has to repair.
        conn.execute("DELETE FROM external_refs WHERE ref_value = ?", ("8002",))
        conn.commit()
        assert store.external_refs.resolve(_GITHUB, _ISSUE, "8002") is None

        hydrate(tmp_path / "projection", store)

        restored = store.external_refs.resolve(_GITHUB, _ISSUE, "8002")
        assert restored is not None, (
            "hydrate did not restore a ref the projection names — it upserts store.objects "
            "only, so an inbound ingest leaves the refs table however it found it"
        )
        assert restored.object_uid == needs_restore.uid

        ref = store.external_refs.resolve(_GITHUB, _ISSUE, "8001")
        assert ref is not None, "the ref that was already there must still exist"
        assert ref.data == _PROVENANCE, (
            "the restore wiped the ref row's provenance. link() is DO UPDATE SET "
            "data=excluded.data and _dumps(None) is '{}' — the same wholesale-replace "
            "fault as ObjectStore.upsert, one table over. The projection carries no "
            f"opinion about this blob, so it must not overwrite it. Got: {ref.data!r}"
        )
        assert ref.object_uid == keeps_blob.uid, "and it must still point at the right object"
