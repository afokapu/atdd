# URN: test:govern-lifecycle:honest-outbox-deferral:C015-UNIT-001-an-undrained-outbox-is-not-a-successful-drain
# Acceptance: acc:govern-lifecycle:C015-UNIT-001-an-undrained-outbox-is-not-a-successful-drain
# WMBT: wmbt:govern-lifecycle:C015
# Phase: GREEN
# Runtime: python
# Layer: unit
# Assertion: behavioral
# Purpose: push_outbox's outcome carries a verdict, so "there was nothing to drain" and "there was nowhere to drain to" stop producing the same answer.
"""C015-UNIT-001 — an undrained outbox is not a successful drain.

``push_outbox`` leaves a message pending when ``providers.get(msg.provider)`` is
None and counts it ``skipped_no_provider``; its caller in ``sync_cli`` returns 1
only if ``pushed.failed``. So a run with **no provider registered** reports zero
failures and exits 0 — the exact output of a run that drained everything. On the
live store that state has held since 2026-07-09: 30 rows pending, 2 ever sent,
``discover_providers()`` empty, and every check of it answered success.

This file holds the four answers a drain can honestly give. The vocabulary is the
one #1719/C013 gave the transition gate, deliberately: the repo should carry one
name for "I could not perform this observation", not two.

RED state: ``atdd.state.sync_engine`` declares no ``OutboxVerdict`` and
``PushResult`` has no verdict to read.
"""
from __future__ import annotations

from typing import List, Optional

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore
from atdd.state.sync_engine import OutboxVerdict, PushOutcome, push_outbox


class FakeProvider:
    """A SyncProvider with no real I/O — records calls, optionally raises."""

    def __init__(self, name: str = "prov", *, fail_on: Optional[str] = None) -> None:
        self.name = name
        self.calls: List = []
        self._fail_on = fail_on

    def push(self, operation, payload) -> Optional[PushOutcome]:
        self.calls.append((operation, payload))
        if self._fail_on == operation:
            raise RuntimeError("provider boom")
        return None


@pytest.fixture()
def store(tmp_path):
    conn = connect(init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite"))
    try:
        yield StateStore(conn)
    finally:
        conn.close()


def test_an_empty_outbox_is_not_applicable_rather_than_a_pass(store):
    """Nothing to drain is a different fact from having drained something.

    Collapsing the two is how a drain that has never had anything to do reads
    identically to one that has just finished doing it.
    """
    result = push_outbox(store, {"prov": FakeProvider("prov")})

    assert result.pending == 0
    assert result.verdict is OutboxVerdict.NOT_APPLICABLE
    assert result.verdict is not OutboxVerdict.PASS


def test_a_run_that_sent_every_pending_row_passes(store):
    """The ordinary green path is untouched by the vocabulary."""
    store.sync.enqueue_outbox("prov", "noop", {})
    store.sync.enqueue_outbox("prov", "noop", {})

    result = push_outbox(store, {"prov": FakeProvider("prov")})

    assert result.pushed == 2 and result.failed == 0
    assert result.verdict is OutboxVerdict.PASS
    assert store.sync.pending_outbox() == []


def test_rows_with_no_registered_provider_could_not_be_checked(store):
    """The defect, stated: a queue with nowhere to go must not report a drain.

    This is the live repository's state — one provider name in the outbox, no
    registration anywhere — and the answer it gave for 25 days was exit 0.
    """
    store.sync.enqueue_outbox("github", "create_issue", {"slug": "x"})

    result = push_outbox(store, {})   # the registry as this repo ships it

    assert result.pushed == 0 and result.failed == 0
    assert result.skipped_no_provider == 1
    assert result.verdict is OutboxVerdict.COULD_NOT_CHECK
    assert result.verdict is not OutboxVerdict.PASS
    assert len(store.sync.pending_outbox()) == 1     # nothing was destroyed either


def test_a_partial_drain_could_not_be_checked_rather_than_passing(store):
    """One deliverable row does not make the run a drain of the queue."""
    store.sync.enqueue_outbox("prov", "noop", {})
    store.sync.enqueue_outbox("jira", "noop", {})

    result = push_outbox(store, {"prov": FakeProvider("prov")})

    assert result.pushed == 1 and result.skipped_no_provider == 1
    assert result.verdict is OutboxVerdict.COULD_NOT_CHECK


def test_a_provider_error_fails_and_is_reported_apart_from_an_absent_provider(store):
    """'The provider rejected this row' and 'no provider exists' need different actions.

    Both leave the row pending, so counts alone cannot separate them — which is
    why the verdict, not the count, is what the caller reads.
    """
    store.sync.enqueue_outbox("prov", "create", {"object_uid": "wi-1"})

    result = push_outbox(store, {"prov": FakeProvider("prov", fail_on="create")})

    assert result.failed == 1 and result.skipped_no_provider == 0
    assert result.verdict is OutboxVerdict.FAIL
    assert result.verdict is not OutboxVerdict.COULD_NOT_CHECK
    assert result.errors, "a failure must name the row it could not push"


def test_the_vocabulary_is_the_one_the_transition_gate_already_uses():
    """#1719/C013 named these four states for the gate. This is the same distinction
    one layer down, so it must not arrive under a second set of names."""
    assert {v.name for v in OutboxVerdict} == {
        "PASS", "FAIL", "COULD_NOT_CHECK", "NOT_APPLICABLE",
    }
