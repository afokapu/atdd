# URN: test:state-store:github-sync:outbox-push-and-inbox-apply
# Issue: #1184 (#1168 Phase 5)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1184 — State Store ⇄ GitHub provider sync (outbox push / inbox apply).

Uses a fake GitHubClient (no live `gh`): pushing the outbox dispatches the right
client ops, records a created issue as an external_ref, and marks messages sent;
a failing op leaves its message pending. Applying the inbox folds GitHub issue
state onto the linked work item and imports new issues.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.integrations.github.state_sync import apply_inbox, push_outbox
from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore


class FakeGitHubClient:
    def __init__(self, *, fail_on=None, next_number="500"):
        self.calls = []
        self._fail_on = fail_on
        self._next_number = next_number

    def create_issue(self, title, body, labels):
        self.calls.append(("create_issue", title, tuple(labels)))
        if self._fail_on == "create_issue":
            raise RuntimeError("gh boom")
        return self._next_number

    def add_label(self, issue_number, label):
        self.calls.append(("add_label", issue_number, label))
        if self._fail_on == "add_label":
            raise RuntimeError("gh boom")

    def add_comment(self, issue_number, body):
        self.calls.append(("add_comment", issue_number, body))


@pytest.fixture()
def store(tmp_path):
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    conn = connect(db)
    try:
        yield StateStore(conn)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Outbox push (local → GitHub)
# --------------------------------------------------------------------------- #
def test_push_create_issue_records_external_ref(store):
    store.objects.upsert("wi-1", "work_item", state="INIT")
    store.sync.enqueue_outbox("github", "create_issue",
                              {"object_uid": "wi-1", "title": "do it", "labels": ["atdd-issue"]})
    client = FakeGitHubClient(next_number="777")

    result = push_outbox(store, client)

    assert result.pushed == 1 and result.failed == 0
    assert ("create_issue", "do it", ("atdd-issue",)) in client.calls
    ref = store.external_refs.resolve("github", "issue", "777")
    assert ref is not None and ref.object_uid == "wi-1"
    assert store.sync.pending_outbox() == []          # marked sent


def test_push_dispatches_label_and_comment(store):
    store.sync.enqueue_outbox("github", "add_label", {"issue_number": 42, "label": "atdd:RED"})
    store.sync.enqueue_outbox("github", "comment", {"issue_number": 42, "body": "hi"})

    result = push_outbox(store, (client := FakeGitHubClient()))

    assert result.pushed == 2
    assert ("add_label", "42", "atdd:RED") in client.calls
    assert ("add_comment", "42", "hi") in client.calls


def test_push_failure_leaves_message_pending(store):
    store.sync.enqueue_outbox("github", "create_issue", {"object_uid": "wi-1", "title": "x"})
    store.objects.upsert("wi-1", "work_item")

    result = push_outbox(store, FakeGitHubClient(fail_on="create_issue"))

    assert result.pushed == 0 and result.failed == 1 and result.errors
    assert len(store.sync.pending_outbox()) == 1       # NOT marked sent → retryable


def test_push_dry_run_sends_nothing(store):
    store.sync.enqueue_outbox("github", "comment", {"issue_number": 1, "body": "x"})
    result = push_outbox(store, (client := FakeGitHubClient()), dry_run=True)
    assert result.pushed == 0 and client.calls == []
    assert len(store.sync.pending_outbox()) == 1


def test_push_unknown_operation_is_isolated_failure(store):
    store.sync.enqueue_outbox("github", "frobnicate", {})
    result = push_outbox(store, FakeGitHubClient())
    assert result.failed == 1 and "unknown outbox operation" in result.errors[0]


# --------------------------------------------------------------------------- #
# Inbox apply (GitHub → local)
# --------------------------------------------------------------------------- #
def test_apply_issue_state_updates_linked_work_item(store):
    store.objects.upsert("wi-1", "work_item", state="RED")
    store.external_refs.link("wi-1", "github", "issue", "900")
    store.sync.enqueue_inbox("github", {"kind": "issue_state", "issue_number": 900, "state": "COMPLETE"})

    result = apply_inbox(store)

    assert result.applied == 1
    assert store.objects.get("wi-1").state == "COMPLETE"
    assert store.sync.pending_inbox() == []           # marked processed


def test_apply_issue_state_without_local_object_is_skipped(store):
    store.sync.enqueue_inbox("github", {"kind": "issue_state", "issue_number": 999, "state": "X"})
    result = apply_inbox(store)
    assert result.applied == 0 and result.skipped == 1


def test_apply_issue_imported_creates_work_item_and_ref(store):
    store.sync.enqueue_inbox("github", {"kind": "issue_imported", "issue_number": 123,
                                        "slug": "imported-thing", "title": "T", "state": "INIT"})
    result = apply_inbox(store)
    assert result.applied == 1
    assert store.objects.get("imported-thing").data["title"] == "T"
    assert store.external_refs.resolve("github", "issue", "123").object_uid == "imported-thing"


def test_apply_dry_run_leaves_inbox_pending(store):
    store.objects.upsert("wi-1", "work_item", state="RED")
    store.external_refs.link("wi-1", "github", "issue", "900")
    store.sync.enqueue_inbox("github", {"kind": "issue_state", "issue_number": 900, "state": "GREEN"})

    apply_inbox(store, dry_run=True)

    assert store.objects.get("wi-1").state == "GREEN"   # state change applied...
    assert len(store.sync.pending_inbox()) == 1         # ...but not marked processed (dry-run)
