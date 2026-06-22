# URN: test:state-store:sync-engine:agnostic-push-and-apply
# Issue: #1201 (refactor of #1184 Phase 5)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1201 — provider-agnostic sync engine.

Core drains the outbox by dispatching to a registered SyncProvider keyed by name
(no GitHub knowledge), records the external ref a push returns, and leaves a
message pending when no provider is registered. apply_inbox is fully generic:
canonical events resolve an external_ref and mutate local state with no provider.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore
from atdd.state.sync_engine import (
    EVENT_EXTERNAL_IMPORTED,
    EVENT_EXTERNAL_STATE,
    PushOutcome,
    apply_inbox,
    push_outbox,
)


class FakeProvider:
    """A SyncProvider with no real I/O — records calls, returns canned outcomes."""

    def __init__(self, name="prov", *, fail_on=None, ref_value="500"):
        self.name = name
        self.calls: List = []
        self._fail_on = fail_on
        self._ref_value = ref_value

    def push(self, operation, payload) -> Optional[PushOutcome]:
        self.calls.append((operation, payload))
        if self._fail_on == operation:
            raise RuntimeError("provider boom")
        if operation == "create":
            return PushOutcome(object_uid=payload.get("object_uid"), ref_kind="issue",
                               ref_value=self._ref_value, ref_data={"src": "x"})
        return None


@pytest.fixture()
def store(tmp_path):
    conn = connect(init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite"))
    try:
        yield StateStore(conn)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# push_outbox — agnostic dispatch by provider name
# --------------------------------------------------------------------------- #
def test_push_dispatches_to_registered_provider_and_records_ref(store):
    store.objects.upsert("wi-1", "work_item")
    store.sync.enqueue_outbox("prov", "create", {"object_uid": "wi-1"})

    prov = FakeProvider("prov", ref_value="777")
    result = push_outbox(store, {"prov": prov})

    assert result.pushed == 1 and result.failed == 0
    assert prov.calls == [("create", {"object_uid": "wi-1"})]
    assert store.external_refs.resolve("prov", "issue", "777").object_uid == "wi-1"
    assert store.sync.pending_outbox() == []


def test_push_without_registered_provider_leaves_pending(store):
    store.sync.enqueue_outbox("jira", "create", {})
    result = push_outbox(store, {"github": FakeProvider("github")})   # no jira provider

    assert result.pushed == 0 and result.skipped_no_provider == 1
    assert len(store.sync.pending_outbox()) == 1      # core never assumes a provider


def test_push_provider_failure_is_isolated_and_retryable(store):
    store.sync.enqueue_outbox("prov", "create", {"object_uid": "wi-1"})
    store.objects.upsert("wi-1", "work_item")
    result = push_outbox(store, {"prov": FakeProvider("prov", fail_on="create")})

    assert result.failed == 1 and result.errors
    assert len(store.sync.pending_outbox()) == 1      # not marked sent


def test_push_outcome_without_ref_records_nothing(store):
    store.sync.enqueue_outbox("prov", "noop", {})
    push_outbox(store, {"prov": FakeProvider("prov")})
    assert store.external_refs.all() == []
    assert store.sync.pending_outbox() == []          # still marked sent


def test_push_multiple_providers_routed_by_name(store):
    store.sync.enqueue_outbox("a", "noop", {})
    store.sync.enqueue_outbox("b", "noop", {})
    pa, pb = FakeProvider("a"), FakeProvider("b")
    push_outbox(store, {"a": pa, "b": pb})
    assert len(pa.calls) == 1 and len(pb.calls) == 1


# --------------------------------------------------------------------------- #
# apply_inbox — fully agnostic, no provider
# --------------------------------------------------------------------------- #
def test_apply_external_state_updates_linked_object(store):
    store.objects.upsert("wi-1", "work_item", state="RED")
    store.external_refs.link("wi-1", "github", "issue", "900")
    store.sync.enqueue_inbox("github", {"kind": EVENT_EXTERNAL_STATE,
                                        "ref_kind": "issue", "ref_value": 900, "state": "COMPLETE"})

    result = apply_inbox(store)

    assert result.applied == 1
    assert store.objects.get("wi-1").state == "COMPLETE"
    assert store.sync.pending_inbox() == []


def test_apply_external_state_no_local_ref_is_skipped(store):
    store.sync.enqueue_inbox("github", {"kind": EVENT_EXTERNAL_STATE,
                                        "ref_kind": "issue", "ref_value": 999, "state": "X"})
    result = apply_inbox(store)
    assert result.applied == 0 and result.skipped == 1


def test_apply_external_imported_upserts_object_and_ref(store):
    store.sync.enqueue_inbox("jira", {"kind": EVENT_EXTERNAL_IMPORTED, "ref_kind": "ticket",
                                      "ref_value": "PROJ-7", "uid": "imported-7",
                                      "state": "INIT", "data": {"title": "T"}})
    result = apply_inbox(store)
    assert result.applied == 1
    assert store.objects.get("imported-7").data["title"] == "T"
    assert store.external_refs.resolve("jira", "ticket", "PROJ-7").object_uid == "imported-7"


def test_apply_is_provider_agnostic_across_providers(store):
    # two different providers, same generic engine, no provider objects involved
    for prov, val in (("github", "1"), ("jira", "2")):
        store.objects.upsert(f"wi-{prov}", "work_item", state="RED")
        store.external_refs.link(f"wi-{prov}", prov, "issue", val)
        store.sync.enqueue_inbox(prov, {"kind": EVENT_EXTERNAL_STATE,
                                        "ref_kind": "issue", "ref_value": val, "state": "DONE"})
    result = apply_inbox(store)
    assert result.applied == 2
    assert store.objects.get("wi-github").state == "DONE"
    assert store.objects.get("wi-jira").state == "DONE"
