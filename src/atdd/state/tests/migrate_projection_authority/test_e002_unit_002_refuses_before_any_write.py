# URN: test:migrate-projection-authority:migrate-store-projection:E002-UNIT-002-refuses-before-any-write
# Acceptance: acc:migrate-projection-authority:E002-UNIT-002-refuses-before-any-write
# WMBT: wmbt:migrate-projection-authority:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A store holding one unmigratable object must refuse the whole migration before any write — no object mutated, no projection file left behind. A half-migrated store is worse than an unmigrated one. Refs #1622.

"""One bad object refuses the whole run, and mutates nothing (E002-UNIT-002).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:E002

The manifest-side migration already holds this line (`C001-UNIT-001`): it validates
every entry before it writes the first byte, because a corpus that is half migrated
cannot be told apart from one that was never migrated, and the operator has no way
back. The store-native migration inherits that obligation and gains a sharper one:
it mutates the store *in place*, so a partial run damages the only surviving source
of truth rather than a derived tree.

RED: there is no store-native migration entrypoint to call. `manifest_migration`
exposes `mint_uids`/`migrate`, and both read `.atdd/manifest.yaml` — the artifact
`decommission-manifest` deleted. The assertion below names that absence directly
rather than dying on an ImportError, so the failure reads as the missing capability
it is.
"""
from __future__ import annotations

import json

from atdd.state import manifest_migration
from atdd.state.work_item_writer import create_work_item

from ._helpers import memory_store

#: The entrypoint CORE-036 must provide: migrate the STORE, not a manifest.
_STORE_MIGRATION_ENTRYPOINTS = ("migrate_store", "mint_store_uids")


def test_an_unmigratable_object_refuses_the_run_and_mutates_nothing() -> None:
    """A single bad object stops the migration before it touches the store."""
    with memory_store() as (conn, store):
        create_work_item(conn, "good-work-item", state="PLANNED", data={"title": "good"})
        create_work_item(conn, "", state="PLANNED", data={"title": "unmigratable"})

        before = {
            obj.uid: (obj.state, json.dumps(obj.data, sort_keys=True))
            for obj in store.objects.list(kind="work_item")
        }

        migrate = next(
            (
                getattr(manifest_migration, name)
                for name in _STORE_MIGRATION_ENTRYPOINTS
                if hasattr(manifest_migration, name)
            ),
            None,
        )
        assert migrate is not None, (
            "no store-native migration entrypoint exists — "
            f"expected one of {list(_STORE_MIGRATION_ENTRYPOINTS)}. "
            "mint_uids/migrate operate on .atdd/manifest.yaml, which "
            "decommission-manifest deleted, so neither can migrate the store (CORE-036)"
        )

        raised = False
        try:
            migrate(conn)
        except Exception:
            raised = True

        assert raised, "an unmigratable object must refuse the whole run"

        after = {
            obj.uid: (obj.state, json.dumps(obj.data, sort_keys=True))
            for obj in store.objects.list(kind="work_item")
        }
        assert after == before, (
            "a refused migration must leave every stored object exactly as it was"
        )
