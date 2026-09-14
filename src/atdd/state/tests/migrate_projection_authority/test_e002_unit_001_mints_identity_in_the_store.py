# URN: test:migrate-projection-authority:migrate-store-projection:E002-UNIT-001-mints-identity-in-the-store
# Acceptance: acc:migrate-projection-authority:E002-UNIT-001-mints-identity-in-the-store
# WMBT: wmbt:migrate-projection-authority:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A store whose work items were written by the live production path (create_work_item, slug-keyed) must be projectable. Today every such object is refused by the contract on its uid and its missing owner_actor, which is the whole of #1622. Refs #1622.

"""The store's own objects must satisfy the projection contract (E002-UNIT-001).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:E002

`create_work_item` is the path EVERY production caller uses — `atdd author issue`
and the coach lifecycle both land here — and it keys the object by its **slug**,
writing that slug into the `objects.uid` column. `mint_work_item`, which mints the
`wi_<ULID>` the contract requires, has no production caller at all.

So the store fills up with objects the projection contract cannot accept, and
`atdd state project` refuses on the first one and writes nothing. The manifest-side
backfill (`manifest_migration.mint_uids`) cannot fix this: it reads
`.atdd/manifest.yaml`, which `decommission-manifest` deleted.

RED: this fails inside `build_documents` with the contract's own refusal — the uid
pattern and the missing `owner_actor` — not on a missing import. That failure IS
the acceptance: it is the exact shape CORE-036 has to make go away.
"""
from __future__ import annotations

import pytest

from atdd.state.projection import ProjectionSchemaError, build_documents
from atdd.state.work_item_writer import create_work_item

from ._helpers import memory_store


def test_store_objects_written_by_the_production_path_are_projectable() -> None:
    """Every work item the live writer produces must yield a projection document."""
    with memory_store() as (conn, store):
        for slug in ("first-work-item", "second-work-item", "third-work-item"):
            create_work_item(conn, slug, state="PLANNED", data={"title": slug})

        assert len(store.objects.list(kind="work_item")) == 3

        try:
            documents = build_documents(store)
        except ProjectionSchemaError as exc:  # pragma: no cover - the RED path
            pytest.fail(
                "the store's own objects are not projectable, so no projection can "
                f"ever be produced from it: {exc}"
            )

        assert set(documents) == {
            obj.uid for obj in store.objects.list(kind="work_item")
        }, "every stored work item must be projected under its own identity"

        for uid, document in documents.items():
            assert document["uid"] == uid
            assert document.get("owner_actor"), (
                f"{uid} carries no owner_actor, which the contract requires"
            )
