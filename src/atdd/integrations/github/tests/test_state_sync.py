# URN: test:state-store:github-provider:push-mapping
# Issue: #1201 (refactor of #1184)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1201 — GitHubSyncProvider maps outbox operations onto the gh client.

The generic drain/record/apply machinery is tested in the core engine
(test_sync_engine.py); here we test only the GitHub-specific provider: each
operation dispatches to the right client call, create_issue returns an external
ref to record, and the provider plugs into the core push_outbox via a fake client.
"""
from __future__ import annotations

import pytest

from atdd.integrations.github.state_sync import GitHubSyncProvider
from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore
from atdd.state.sync_engine import push_outbox


class FakeGitHubClient:
    def __init__(self, *, number="500"):
        self.calls = []
        self._number = number

    def create_issue(self, title, body, labels):
        self.calls.append(("create_issue", title, tuple(labels)))
        return self._number

    def add_label(self, issue_number, label):
        self.calls.append(("add_label", issue_number, label))

    def add_comment(self, issue_number, body):
        self.calls.append(("add_comment", issue_number, body))


def test_provider_create_issue_returns_external_ref():
    prov = GitHubSyncProvider(FakeGitHubClient(number="777"))
    outcome = prov.push("create_issue", {"object_uid": "wi-1", "title": "t", "labels": ["atdd-issue"]})
    assert outcome.object_uid == "wi-1" and outcome.ref_kind == "issue" and outcome.ref_value == "777"
    assert outcome.records_ref


def test_provider_label_and_comment_return_none():
    client = FakeGitHubClient()
    prov = GitHubSyncProvider(client)
    assert prov.push("add_label", {"issue_number": 42, "label": "atdd:RED"}) is None
    assert prov.push("comment", {"issue_number": 42, "body": "hi"}) is None
    assert ("add_label", "42", "atdd:RED") in client.calls
    assert ("add_comment", "42", "hi") in client.calls


def test_provider_unknown_operation_raises():
    with pytest.raises(ValueError):
        GitHubSyncProvider(FakeGitHubClient()).push("frobnicate", {})


def test_provider_plugs_into_core_push_outbox(tmp_path):
    conn = connect(init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite"))
    try:
        store = StateStore(conn)
        store.objects.upsert("wi-1", "work_item")
        store.sync.enqueue_outbox("github", "create_issue", {"object_uid": "wi-1", "title": "x"})

        result = push_outbox(store, {"github": GitHubSyncProvider(FakeGitHubClient(number="909"))})

        assert result.pushed == 1
        assert store.external_refs.resolve("github", "issue", "909").object_uid == "wi-1"
        assert store.sync.pending_outbox() == []
    finally:
        conn.close()
