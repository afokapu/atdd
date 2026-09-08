# URN: test:project-shared-state:mint-object-identity:Y002-UNIT-001-addresses-every-live-uid-form
# Acceptance: acc:project-shared-state:Y002-UNIT-001-addresses-every-live-uid-form
# WMBT: wmbt:project-shared-state:Y002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: `atdd state object rename` must address a work item by the uid the store actually holds — both live slug forms — not only the wi_<ULID> form that was never minted. Refs #1653.
"""Rename addresses every live uid form, not only the minted one (Y002-UNIT-001).

wagon: project-shared-state | feature: mint-object-identity | phase: RED
WMBT: wmbt:project-shared-state:Y002

Measured on the Control Root store (#1653): 822 work items, **zero** carrying a
minted ``wi_<ULID>`` uid. 633 are ``unverified:<slug>`` and 189 are bare slugs —
the two forms the authoring path actually mints (``author_publish.derive_slug``
documents the slug as "the work_item uid"). The rename verb gated its argument on
``^wi_[0-9A-HJKMNP-TV-Z]{26}$``, so it addressed 0 of 822.

Both forms are exercised because widening to one of them would leave the verb
dead against the other — 189 or 633 objects still unaddressable.
"""
from __future__ import annotations

import pytest

from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.work_item_writer import rename_work_item

from ._helpers import memory_store

#: The two uid forms the live store actually holds. Neither is ``wi_<ULID>``.
LIVE_UID_FORMS = (
    pytest.param("unverified:issue-1004", id="unverified-form"),
    pytest.param("store-github-sync-token", id="bare-slug-form"),
)


@pytest.mark.parametrize("uid", LIVE_UID_FORMS)
def test_y002_unit_001_addresses_every_live_uid_form(uid) -> None:
    """A work item held under a live slug uid is renamable by that uid."""
    with memory_store() as (conn, store):
        store.objects.upsert(
            uid, WORK_ITEM_KIND, state="INIT",
            data={"slug": "old-slug", "title": "Old Title", "owner_actor": "dev-a"},
        )

        renamed = rename_work_item(conn, uid, slug="new-slug", title="New Title")

        # The rename lands on display metadata...
        assert renamed.data["slug"] == "new-slug"
        assert renamed.data["title"] == "New Title"

        # ...and identity does not move (Y001): same uid, still one object.
        assert renamed.uid == uid
        stored = store.objects.get(uid)
        assert stored is not None and stored.uid == uid
        assert stored.kind == WORK_ITEM_KIND
        assert len(store.objects.list(kind=WORK_ITEM_KIND)) == 1
