# URN: component:state:test-support:provenance:backend:tests
# Runtime: python
# Purpose: Prove the #1557 provenance audit can FAIL — one injected fault per
#          clause — and that it fails closed rather than passing vacuously.

"""Fault injection for the work-item provenance audit (#1557).

A ``clean_baseline_is_zero`` assertion on a function that cannot emit passes
forever. Every clause the audit can report gets an injected fault here that
proves the audit actually reports it, and the fail-closed path gets a probe that
proves an unreadable store *raises* instead of returning an empty list — the two
outcomes a caller cannot tell apart if the audit is silently toothless.

Hermetic: an in-memory store, no provider, no network (I7).
"""
from __future__ import annotations

import sqlite3

import pytest

from atdd.state import provenance
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.tests._fixtures import memory_store


def _work_item(store, uid: str = "wi-1"):
    return store.objects.upsert(uid, WORK_ITEM_KIND, state="INIT")


# --------------------------------------------------------------------------- #
# The sanctioned path passes
# --------------------------------------------------------------------------- #
def test_sanctioned_first_event_is_clean():
    """A work item stamped by a sanctioned authoring command reports nothing."""
    with memory_store() as (conn, store):
        _work_item(store)
        provenance.record_authored(store, "wi-1", command="atdd author issue")

        assert provenance.audit_work_items(conn) == []


def test_empty_store_reports_nothing_and_does_not_raise():
    """No work items is not the same as unreadable — it has nothing to say."""
    with memory_store() as (conn, _store):
        assert provenance.audit_work_items(conn) == []


def test_later_events_do_not_disturb_a_sanctioned_first_event():
    """Provenance is about the FIRST event; ordinary activity after it is fine."""
    with memory_store() as (conn, store):
        _work_item(store)
        provenance.record_authored(store, "wi-1", command="atdd author issue")
        store.events.append("issue_revised", object_uid="wi-1")
        store.events.append("phase_changed", object_uid="wi-1")

        assert provenance.audit_work_items(conn) == []


# --------------------------------------------------------------------------- #
# Fault injection — one per clause the audit can report
# --------------------------------------------------------------------------- #
def test_work_item_with_no_events_is_a_violation():
    """The bare out-of-band create: an object with no provenance at all."""
    with memory_store() as (conn, store):
        _work_item(store)

        findings = provenance.audit_work_items(conn)

        assert [f.clause for f in findings] == [provenance.CLAUSE_NO_EVENTS]
        assert findings[0].uid == "wi-1"


def test_reconciled_first_event_is_a_violation():
    """THE INVERSION: repair records the violation, it does not absolve it."""
    with memory_store() as (conn, store):
        _work_item(store)
        provenance.record_reconciled(
            store, "wi-1", discovered_via="atdd coach reconcile"
        )

        findings = provenance.audit_work_items(conn)

        assert [f.clause for f in findings] == [provenance.CLAUSE_RECONCILED]
        assert "atdd coach reconcile" in findings[0].detail


def test_unsanctioned_first_event_is_a_violation():
    """The allowlist admits nothing it was not told about.

    An event type nobody anticipated — not forbidden anywhere, simply not
    sanctioned — must still be caught. This is the case a blocklist would let
    through, and it is why the rule is written as an allowlist.
    """
    with memory_store() as (conn, store):
        _work_item(store)
        store.events.append("some_future_event_nobody_thought_of", object_uid="wi-1")

        findings = provenance.audit_work_items(conn)

        assert [f.clause for f in findings] == [provenance.CLAUSE_UNSANCTIONED_FIRST]


def test_a_sanctioned_event_arriving_second_does_not_launder_the_record():
    """Provenance is history: you cannot back-date it by authoring afterwards."""
    with memory_store() as (conn, store):
        _work_item(store)
        store.events.append("issue_revised", object_uid="wi-1")
        store.events.append(
            provenance.WORK_ITEM_AUTHORED, object_uid="wi-1", payload={"command": "x"}
        )

        findings = provenance.audit_work_items(conn)

        assert [f.clause for f in findings] == [provenance.CLAUSE_UNSANCTIONED_FIRST]


def test_only_work_items_are_audited():
    """Other kinds (agent_session, release, …) carry no authoring invariant."""
    with memory_store() as (conn, store):
        store.objects.upsert("sess-1", "agent_session")

        assert provenance.audit_work_items(conn) == []


# --------------------------------------------------------------------------- #
# Fail closed — an inability to look must never read as a pass
# --------------------------------------------------------------------------- #
def test_unreadable_store_raises_rather_than_returning_empty():
    """A dropped ``objects`` table must NOT come back as 'nothing wrong'.

    Returning ``[]`` here would be indistinguishable from a clean store, which
    is precisely the fail-open failure this rule exists to close.
    """
    with memory_store() as (conn, _store):
        conn.execute("DROP TABLE objects")

        with pytest.raises(provenance.ProvenanceStoreUnreadable):
            provenance.audit_work_items(conn)


def test_unreadable_event_log_raises_rather_than_reporting_clean():
    """Objects readable but events not: still an inability to look, not a pass.

    Without this, a missing ``events`` table would report every work item as
    ``no_provenance_event`` — plausible-looking findings manufactured from a
    broken store rather than a real audit.
    """
    with memory_store() as (conn, store):
        _work_item(store)
        conn.execute("DROP TABLE events")

        with pytest.raises(provenance.ProvenanceStoreUnreadable):
            provenance.audit_work_items(conn)


def test_closed_connection_raises():
    """The plainest unreadable store there is."""
    conn = sqlite3.connect(":memory:")
    conn.close()

    with pytest.raises(provenance.ProvenanceStoreUnreadable):
        provenance.audit_work_items(conn)


# --------------------------------------------------------------------------- #
# Writer contracts
# --------------------------------------------------------------------------- #
def test_record_authored_refuses_an_unsanctioned_event_type():
    """A call site may not invent its own sanctioned stamp."""
    with memory_store() as (_conn, store):
        _work_item(store)

        with pytest.raises(ValueError):
            provenance.record_authored(
                store, "wi-1", command="x", event_type="totally_fine_honest"
            )


def test_record_authored_is_idempotent():
    """Re-authoring (the create is an upsert) must not append a second stamp.

    If it did, "first event" would still be right — but the log would grow one
    authoring event per re-author, and a record's provenance would become a
    count rather than a fact.
    """
    with memory_store() as (_conn, store):
        _work_item(store)
        provenance.record_authored(store, "wi-1", command="atdd author issue")
        provenance.record_authored(store, "wi-1", command="atdd author issue")

        stamps = [
            e for e in store.events.list(object_uid="wi-1")
            if e.event_type in provenance.PROVENANCE_EVENTS
        ]
        assert len(stamps) == 1


def test_reconcile_never_overwrites_sanctioned_provenance():
    """Repair adds evidence where there was none; it never demotes a good record."""
    with memory_store() as (conn, store):
        _work_item(store)
        provenance.record_authored(store, "wi-1", command="atdd author issue")
        provenance.record_reconciled(
            store, "wi-1", discovered_via="atdd coach reconcile"
        )

        assert provenance.audit_work_items(conn) == []


def test_reconcile_stamp_is_not_in_the_allowlist():
    """The load-bearing fact of the whole inversion, asserted directly."""
    assert provenance.RECONCILED not in provenance.SANCTIONED_AUTHORING_EVENTS


def test_the_vocabulary_covers_all_three_creates():
    """Designed once (#1557 decision 6), not invented per-create later."""
    assert provenance.SANCTIONED_AUTHORING_EVENTS == {
        provenance.WORK_ITEM_AUTHORED,
        provenance.PULL_REQUEST_AUTHORED,
        provenance.BRANCH_AUTHORED,
    }
