# URN: test:project-shared-state:mint-object-identity:E004-UNIT-001-mints-unique-immutable-uid
# Acceptance: acc:project-shared-state:E004-UNIT-001-mints-unique-immutable-uid
# WMBT: wmbt:project-shared-state:E004
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Creating a work item mints a globally unique wi_ uid; a later write that tries to rewrite that uid is refused and the stored uid is unchanged. Refs #1433.
"""Identity is minted once and never moves (E004-UNIT-001).

wagon: project-shared-state | feature: mint-object-identity | phase: RED
WMBT: wmbt:project-shared-state:E004

Two creates carrying the *same slug* must still be two distinct objects: the slug
is a label, the uid is the identity (spec §10 rule 1). And once minted, no write
may rewrite it — a moving uid would silently orphan the object's projection file
and its whole git history. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest

from atdd.state.identity import UID_RE, UidImmutableError
from atdd.state.work_item_writer import mint_work_item, update_work_item

from ._helpers import memory_store


def test_e004_unit_001_mints_unique_immutable_uid(tmp_path) -> None:
    """Same-slug creates mint distinct uids; a rewrite attempt is refused."""
    with memory_store() as (conn, store):
        first = mint_work_item(conn, slug="feature-x", owner_actor="dev-a")
        second = mint_work_item(conn, slug="feature-x", owner_actor="dev-a")

        # The two minted uids are distinct and match the wi_ identity shape.
        assert first.uid != second.uid
        assert UID_RE.match(first.uid), first.uid
        assert UID_RE.match(second.uid), second.uid

        # A later update that tries to rewrite one uid is refused...
        with pytest.raises(UidImmutableError):
            update_work_item(conn, first.uid, {"uid": second.uid, "slug": "renamed"})

        # ...and the stored uid — and everything else — is unchanged.
        stored = store.objects.get(first.uid)
        assert stored is not None
        assert stored.uid == first.uid
        assert stored.data["slug"] == "feature-x"
        assert store.objects.get(second.uid) is not None
