# URN: test:state-store:work-item-reader:cold-start-provider-seed
# Issue: #1270 Slice G (delete the manifest mirror; re-wire the cold-start seed)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 Slice G — a cold store self-seeds from a registered SyncProvider.

The ``.atdd/manifest.yaml`` mirror (and the reader's manifest auto-import) were
deleted. The cold-start seed is now **provider-agnostic**: on first read of an
empty store the reader asks every registered
:class:`~atdd.state.sync_engine.SyncProvider` to ``ingest`` from its remote and
drains the resulting canonical events into local state. Core imports no provider,
so this proves the seam end-to-end with a fake in-memory provider that mimics
GitHub — with **no manifest present**.

RED before the re-wire: ``_auto_import_if_empty`` called ``import_manifest``,
which is a no-op when no ``.atdd/manifest.yaml`` exists → the store stays empty →
``reader.status(...)`` returns ``None`` and the first assertion fails. GREEN after
the re-wire to ``ingest_inbox``/``apply_inbox`` over registered providers.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from atdd.state.manifest_import import GITHUB_PROVIDER
from atdd.state.providers import clear_providers, register_provider
from atdd.state.store import StateStore
from atdd.state.sync_engine import EVENT_EXTERNAL_IMPORTED, PushOutcome, SyncProvider
from atdd.state.work_item_reader import WorkItemReader


class _FakeGitHubProvider:
    """An in-memory :class:`SyncProvider` that mimics GitHub issues.

    ``ingest(store)`` enqueues a couple of canonical ``EVENT_EXTERNAL_IMPORTED``
    inbox events (as a real GitHub provider would after polling), linked under the
    ``github`` provider / ``issue`` ref so the store-backed reader resolves them
    by issue number. ``push`` is a no-op (this test drives the ingest half only).
    """

    def __init__(self, issues: List[Dict[str, Any]]) -> None:
        self.name = "fake-github"
        self._issues = issues
        self.ingest_calls = 0

    def push(self, operation: str, payload: Dict[str, Any]) -> Optional[PushOutcome]:
        return None

    def ingest(self, store: StateStore) -> None:
        self.ingest_calls += 1
        for issue in self._issues:
            store.sync.enqueue_inbox(
                GITHUB_PROVIDER,
                {
                    "kind": EVENT_EXTERNAL_IMPORTED,
                    "uid": issue["slug"],
                    "object_kind": "work_item",
                    "ref_kind": "issue",
                    "ref_value": str(issue["number"]),
                    "state": issue["status"],
                    "data": {
                        "train": issue.get("train"),
                        "branch": issue.get("branch"),
                        "wagon": issue.get("wagon"),
                        "issue_number": issue["number"],
                    },
                },
            )


_ISSUES = [
    {"slug": "seeded-alpha", "number": 5001, "status": "PLANNED",
     "train": "0002", "branch": "feat/alpha", "wagon": "govern-lifecycle"},
    {"slug": "seeded-beta", "number": 5002, "status": "RED",
     "train": "0003", "branch": "fix/beta", "wagon": "author-plan-substrate"},
]


@pytest.fixture(autouse=True)
def _isolate_providers():
    """No provider leaks into (or out of) this test — core registers none."""
    clear_providers()
    try:
        yield
    finally:
        clear_providers()


def _control_root_with_no_manifest(tmp_path):
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    assert not (tmp_path / ".atdd" / "manifest.yaml").exists()
    return tmp_path, tmp_path / ".atdd" / "state" / "state.sqlite"


def test_cold_store_self_seeds_from_registered_provider(tmp_path):
    """Empty store + NO manifest + a registered provider ⇒ the reader self-seeds
    from the provider's ingest() and returns the ingested work items."""
    root, db = _control_root_with_no_manifest(tmp_path)
    provider = _FakeGitHubProvider(_ISSUES)
    register_provider(provider.name, lambda: provider)

    # Opening the reader triggers the cold-start seed on the empty store.
    with WorkItemReader(control_root=root, db_path=db) as reader:
        assert reader.status(5001) == "PLANNED"
        assert reader.train(5001) == "0002"
        assert reader.branch(5001) == "feat/alpha"
        assert reader.wagon(5001) == "govern-lifecycle"

        assert reader.status(5002) == "RED"
        assert reader.wagon(5002) == "author-plan-substrate"

    # The provider was actually consulted, and the store was self-seeded with no
    # manifest ever present on disk.
    assert provider.ingest_calls == 1
    assert not (root / ".atdd" / "manifest.yaml").exists()
    assert reader.issue_wagon_map is not None  # sanity: reader object usable


def test_cold_store_with_no_provider_reads_none(tmp_path):
    """Empty store + NO manifest + ZERO registered providers ⇒ reads return None
    gracefully (no crash) — core stays provider-agnostic."""
    root, db = _control_root_with_no_manifest(tmp_path)
    # No register_provider call — discover_providers() returns {}.
    with WorkItemReader(control_root=root, db_path=db) as reader:
        assert reader.status(5001) is None
        assert reader.train(5001) is None
        assert reader.branch(5001) is None
    assert not (root / ".atdd" / "manifest.yaml").exists()


def test_seed_runs_at_most_once_non_empty_store_untouched(tmp_path):
    """A non-empty store is left untouched: a second reader does not re-ingest."""
    root, db = _control_root_with_no_manifest(tmp_path)
    provider = _FakeGitHubProvider(_ISSUES)
    register_provider(provider.name, lambda: provider)

    with WorkItemReader(control_root=root, db_path=db) as reader:
        assert reader.status(5001) == "PLANNED"
    assert provider.ingest_calls == 1

    # Second open: the store already holds work items → no re-ingest.
    with WorkItemReader(control_root=root, db_path=db) as reader2:
        assert reader2.status(5001) == "PLANNED"
    assert provider.ingest_calls == 1


def test_fake_provider_satisfies_sync_provider_protocol():
    """The fake provider structurally satisfies the SyncProvider protocol."""
    provider: SyncProvider = _FakeGitHubProvider([])
    assert callable(provider.push)
    assert provider.name == "fake-github"
