# URN: test:govern-lifecycle:honest-outbox-deferral:C015-UNIT-003-the-backlog-is-reported-with-the-age-of-its-oldest-row
# Acceptance: acc:govern-lifecycle:C015-UNIT-003-the-backlog-is-reported-with-the-age-of-its-oldest-row
# WMBT: wmbt:govern-lifecycle:C015
# Phase: GREEN
# Runtime: python
# Layer: unit
# Assertion: behavioral
# Purpose: The pending backlog is reported with the enqueue time of its oldest row and broken down by provider, so accumulation is legible without querying SQLite by hand.
"""C015-UNIT-003 — the backlog is reported with the age of its oldest row.

Since when matters more than how many. Thirty pending rows is a number an
operator can read as a busy queue; thirty pending rows whose oldest was enqueued
on 2026-07-09 is a queue that has not moved in 25 days. It was the age, not the
size, that made this defect visible — and the age was only available by opening
the SQLite file by hand, because ``pending_outbox`` does not carry ``created_at``
and nothing summarises the table.

RED state: ``SyncStore`` has no ``outbox_backlog``.
"""
from __future__ import annotations

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore


@pytest.fixture()
def store(tmp_path):
    conn = connect(init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite"))
    try:
        yield StateStore(conn)
    finally:
        conn.close()


def _enqueue_at(store: StateStore, provider: str, when: str) -> int:
    """Enqueue a row and backdate it, so ages are asserted rather than simulated."""
    outbox_id = store.sync.enqueue_outbox(provider, "noop", {})
    with store.conn:
        store.conn.execute("UPDATE outbox SET created_at=? WHERE id=?", (when, outbox_id))
    return outbox_id


def test_the_backlog_names_the_enqueue_time_of_its_oldest_pending_row(store):
    """The figure that made the defect visible, available without opening SQLite."""
    _enqueue_at(store, "github", "2026-07-30 09:20:09")
    _enqueue_at(store, "github", "2026-07-09 00:14:16")   # the oldest
    _enqueue_at(store, "github", "2026-07-14 12:57:28")

    backlog = store.sync.outbox_backlog()

    assert backlog.pending == 3
    assert backlog.oldest_enqueued_at == "2026-07-09 00:14:16"


def test_the_backlog_is_broken_down_by_provider_so_one_stuck_name_is_attributable(store):
    """A total averages a single unregistered provider into the rest of the queue."""
    _enqueue_at(store, "github", "2026-07-09 00:14:16")
    _enqueue_at(store, "github", "2026-07-30 09:20:09")
    _enqueue_at(store, "release", "2026-07-14 12:57:28")

    backlog = store.sync.outbox_backlog()

    assert backlog.by_provider == {"github": 2, "release": 1}


def test_an_empty_outbox_reports_zero_explicitly(store):
    """A silent report must not be readable as a clean one — the #1670 shape."""
    backlog = store.sync.outbox_backlog()

    assert backlog.pending == 0
    assert backlog.oldest_enqueued_at is None
    assert backlog.by_provider == {}


def test_rows_that_reached_a_terminal_state_are_excluded_from_the_backlog(store):
    """A sent row is not a backlog row; counting it would inflate the figure the
    operator is being asked to act on."""
    sent = _enqueue_at(store, "github", "2026-07-09 00:14:16")
    _enqueue_at(store, "github", "2026-07-30 09:20:09")
    store.sync.mark_sent(sent)

    backlog = store.sync.outbox_backlog()

    assert backlog.pending == 1
    assert backlog.oldest_enqueued_at == "2026-07-30 09:20:09"
    assert backlog.by_provider == {"github": 1}
