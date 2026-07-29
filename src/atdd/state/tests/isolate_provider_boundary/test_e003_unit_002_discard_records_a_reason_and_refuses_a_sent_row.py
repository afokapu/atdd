# URN: test:isolate-provider-boundary:surface-undrainable-outbox:E003-UNIT-002-discard-records-a-reason-and-refuses-a-sent-row
# Acceptance: acc:isolate-provider-boundary:E003-UNIT-002-discard-records-a-reason-and-refuses-a-sent-row
# WMBT: wmbt:isolate-provider-boundary:E003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: An undeliverable outbox row leaves the queue only against a recorded, non-empty reason and is preserved rather than deleted; an already-sent row cannot be discarded because its side-effect happened on the remote; and an existing disposition cannot be silently overwritten. Refs #1655.
"""A discard with no reason is a delete with extra steps (E003-UNIT-002).

wagon: isolate-provider-boundary | feature: surface-undrainable-outbox | phase: RED
WMBT: wmbt:isolate-provider-boundary:E003

Before migration v4 a stranded row had two futures — sit pending forever, or be
``DELETE``d. The first produced the backlog #1655 triaged. The second destroys the
record that the store ever made the decision, which for a queue whose rows *are*
decisions (a version to publish, an issue to file) is the worse of the two.

So the third way has to earn its status. These acceptances pin the three refusals
that make ``discarded`` mean something: no reason, no discard; a completed
side-effect cannot be retroactively un-decided; and a recorded reason is not
overwritable by a later, vaguer one.
"""
from __future__ import annotations

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore


@pytest.fixture()
def store(tmp_path) -> StateStore:
    conn = connect(init_state_store(db_path=tmp_path / "state.sqlite"))
    return StateStore(conn)


def _status(store: StateStore, outbox_id: int) -> str:
    row = store.conn.execute("SELECT status FROM outbox WHERE id=?", (outbox_id,)).fetchone()
    return row["status"]


def test_discard_without_a_reason_is_refused(store: StateStore) -> None:
    """The reason is the entire point of the status, so its absence is fatal."""
    row_id = store.sync.enqueue_outbox("github", "create_issue", {"title": "x"})

    for empty in ("", "   ", "\n"):
        with pytest.raises(ValueError, match="without a reason"):
            store.sync.discard(row_id, empty)

    assert _status(store, row_id) == "pending", "a refused discard must change nothing"


def test_a_pending_row_is_discarded_with_its_reason_and_is_preserved(store: StateStore) -> None:
    """The row survives the discard — that is what distinguishes it from a delete."""
    row_id = store.sync.enqueue_outbox("github", "version_decided", {"version": "4.16.0"})

    store.sync.discard(row_id, "  version 4.16.0 superseded by v4.28.0  ")

    assert _status(store, row_id) == "discarded"

    row = store.conn.execute(
        "SELECT disposition, disposed_at, payload FROM outbox WHERE id=?", (row_id,)
    ).fetchone()
    assert row["disposition"] == "version 4.16.0 superseded by v4.28.0", "reason stored, trimmed"
    assert row["disposed_at"], "when it was retired is part of the record"
    assert "4.16.0" in row["payload"], "the decision itself is still readable afterwards"

    # It leaves the drain queue without leaving the audit trail.
    assert row_id not in {m.id for m in store.sync.pending_outbox()}
    listed = {m.id: m for m in store.sync.all_outbox()}
    assert listed[row_id].disposition == "version 4.16.0 superseded by v4.28.0"


def test_a_failed_row_can_also_be_discarded(store: StateStore) -> None:
    """`failed` is undeliverable too, and must not be the one status with no way out."""
    row_id = store.sync.enqueue_outbox("github", "version_decided", {"version": "3.149.1"})
    store.conn.execute("UPDATE outbox SET status='failed' WHERE id=?", (row_id,))
    store.conn.commit()

    store.sync.discard(row_id, "version 3.149.1 superseded")

    assert _status(store, row_id) == "discarded"


def test_discarding_an_already_sent_row_is_refused(store: StateStore) -> None:
    """Its side-effect happened on the remote; calling that 'discarded' is a worse lie."""
    row_id = store.sync.enqueue_outbox("github", "create_issue", {"title": "already filed"})
    store.sync.mark_sent(row_id)

    with pytest.raises(ValueError, match="already 'sent'"):
        store.sync.discard(row_id, "changed my mind")

    assert _status(store, row_id) == "sent", "a sent row is immutable"


def test_a_recorded_disposition_is_not_silently_overwritten(store: StateStore) -> None:
    """The first reason is the one that was true when the decision was retired."""
    row_id = store.sync.enqueue_outbox("github", "create_issue", {"title": "x"})
    store.sync.discard(row_id, "abandoned; never re-attempted")

    with pytest.raises(ValueError, match="re-discard"):
        store.sync.discard(row_id, "something vaguer")

    row = store.conn.execute(
        "SELECT disposition FROM outbox WHERE id=?", (row_id,)
    ).fetchone()
    assert row["disposition"] == "abandoned; never re-attempted"


def test_discarding_a_row_that_does_not_exist_is_refused(store: StateStore) -> None:
    """A no-op that reports success would let a typo read as a cleared backlog."""
    with pytest.raises(ValueError, match="no such outbox row"):
        store.sync.discard(4242, "whatever")
