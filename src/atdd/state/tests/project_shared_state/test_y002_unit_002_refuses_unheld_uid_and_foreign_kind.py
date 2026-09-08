# URN: test:project-shared-state:mint-object-identity:Y002-UNIT-002-refuses-unheld-uid-and-foreign-kind
# Acceptance: acc:project-shared-state:Y002-UNIT-002-refuses-unheld-uid-and-foreign-kind
# WMBT: wmbt:project-shared-state:Y002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Dropping the uid shape gate must not let rename address a uid the store does not hold, nor rewrite the kind of a non-work_item object that the shape gate was incidentally shielding. Refs #1653.
"""Rename refuses what the store does not hold, and refuses a foreign kind (Y002-UNIT-002).

wagon: project-shared-state | feature: mint-object-identity | phase: RED
WMBT: wmbt:project-shared-state:Y002

The shape gate was doing two jobs at once. Only one of them was legitimate:

1. *Rejecting a typo* — but ``^wi_...$`` rejected every live uid too, so this job
   is better done by store membership: the uid is whatever the store holds.
2. *Incidentally shielding other kinds.* ``update_work_item`` upserts with
   ``WORK_ITEM_KIND``, so addressing an ``agent_session`` / ``release`` /
   ``hub_adapter`` object would silently rewrite its ``kind``. No live uid of
   those kinds is ``wi_``-shaped, so the shape gate hid this. Removing the gate
   exposes it, which is why the kind guard must land in the same change —
   mirroring the one ``revise_work_item_issue`` already carries.
"""
from __future__ import annotations

import pytest

from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.work_item_writer import rename_work_item

from ._helpers import memory_store

#: A real non-work_item uid from the live store, with its real kind.
FOREIGN_UID, FOREIGN_KIND = "claude:6453e644-64cd-4254-add5-fa30135b52b1", "agent_session"


def test_y002_unit_002_refuses_a_uid_the_store_does_not_hold() -> None:
    """An unheld uid is refused as not-found, and nothing is written."""
    with memory_store() as (conn, store):
        store.objects.upsert(
            "held-work-item", WORK_ITEM_KIND, state="INIT", data={"slug": "held"},
        )

        with pytest.raises(KeyError):
            rename_work_item(conn, "no-such-work-item", title="New Title")

        # The refusal wrote nothing — no object was conjured by the failed address.
        assert store.objects.get("no-such-work-item") is None
        assert len(store.objects.list(kind=WORK_ITEM_KIND)) == 1


def test_y002_unit_002_refuses_a_foreign_kind_without_rewriting_it() -> None:
    """An object of another kind is refused *by kind*, and its stored kind is unchanged.

    The refusal reason is asserted, not merely the refusal. Today's shape gate also
    rejects this uid — but for the wrong reason, and that reason is about to be
    removed. Pinning the message keeps the guard honest once it is the kind check
    doing the work.
    """
    with memory_store() as (conn, store):
        store.objects.upsert(
            FOREIGN_UID, FOREIGN_KIND, state=None, data={"provider": "claude"},
        )

        with pytest.raises(ValueError) as excinfo:
            rename_work_item(conn, FOREIGN_UID, title="Hijacked")

        message = str(excinfo.value)
        assert FOREIGN_KIND in message, f"refusal must name the offending kind: {message!r}"
        assert "not a work-item uid" not in message, (
            f"refused on uid shape, not on kind: {message!r}"
        )

        # The agent_session is still an agent_session — not silently promoted.
        stored = store.objects.get(FOREIGN_UID)
        assert stored is not None
        assert stored.kind == FOREIGN_KIND
        assert "title" not in stored.data
        assert store.objects.list(kind=WORK_ITEM_KIND) == []
