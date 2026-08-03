# URN: test:state-store:provider-registry:agnostic-seam
# Issue: #1364 (ext#40 Phase 2 core seam)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1364 — provider-agnostic SyncProvider registration seam.

`atdd state sync` loads *registered* providers by name instead of hardcoding
GitHub. A provider registers in-process via ``register_provider`` (the PRIMARY
mechanism — atdd extensions are directory-based, not pip distributions, so
entry-point discovery finds nothing from them) or via the
``atdd.state.sync_providers`` entry-point group (SECONDARY — for a genuinely
pip-installed provider package). With zero providers, sync is pure-local. Core
imports no provider (no GitHub) anywhere on the sync path.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.providers import (
    clear_providers,
    discover_providers,
    register_provider,
    registered_names,
    unregister_provider,
)
from atdd.state.store import StateStore
from atdd.state.sync_engine import (
    EVENT_EXTERNAL_IMPORTED,
    EVENT_EXTERNAL_STATE,
    PushOutcome,
    apply_inbox,
    ingest_inbox,
    push_outbox,
)


@pytest.fixture()
def store(tmp_path):
    conn = connect(init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite"))
    try:
        yield StateStore(conn)
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _clean_registry():
    """The registry is process-global; isolate every test."""
    clear_providers()
    yield
    clear_providers()


class FakePushProvider:
    """Push-only SyncProvider — records calls, returns canned outcomes, no I/O."""

    def __init__(self, name: str = "prov", ref_value: str = "500"):
        self.name = name
        self.calls: list = []
        self._ref_value = ref_value

    def push(self, operation: str, payload: dict) -> Optional[PushOutcome]:
        self.calls.append((operation, payload))
        if operation == "create":
            return PushOutcome(object_uid=payload.get("object_uid"), ref_kind="issue",
                               ref_value=self._ref_value)
        return None


class FakeIngestProvider(FakePushProvider):
    """A provider that also fills the inbox from a canned 'remote' snapshot."""

    def __init__(self, name: str = "prov", events: Optional[list] = None):
        super().__init__(name=name)
        self._events = events or []

    def ingest(self, store: StateStore) -> None:
        for ev in self._events:
            store.sync.enqueue_inbox(self.name, ev)


# --------------------------------------------------------------------------- #
# registry / discovery
# --------------------------------------------------------------------------- #
def test_register_then_discover_returns_provider():
    register_provider("prov", lambda: FakePushProvider("prov"))
    providers = discover_providers()
    assert "prov" in providers and providers["prov"].name == "prov"


def test_registered_names_lists_registrations():
    register_provider("a", lambda: FakePushProvider("a"))
    register_provider("b", lambda: FakePushProvider("b"))
    assert registered_names() == ["a", "b"]


def test_unregister_removes_provider():
    register_provider("prov", lambda: FakePushProvider("prov"))
    unregister_provider("prov")
    assert "prov" not in discover_providers()


def test_no_providers_yields_empty_mapping():
    assert discover_providers() == {}


# --------------------------------------------------------------------------- #
# push via the seam (outbox drains through a registered provider)
# --------------------------------------------------------------------------- #
def test_push_drains_outbox_via_registered_provider(store):
    store.objects.upsert("wi-1", "work_item")
    store.sync.enqueue_outbox("prov", "create", {"object_uid": "wi-1"})
    register_provider("prov", lambda: FakePushProvider("prov", ref_value="777"))

    result = push_outbox(store, discover_providers())

    assert result.pushed == 1
    assert store.external_refs.resolve("prov", "issue", "777").object_uid == "wi-1"
    assert store.sync.pending_outbox() == []


def test_push_with_no_provider_stays_pending(store):
    store.sync.enqueue_outbox("prov", "create", {})
    result = push_outbox(store, discover_providers())  # nothing registered → pure-local

    assert result.pushed == 0
    assert len(store.sync.pending_outbox()) == 1


# --------------------------------------------------------------------------- #
# ingest via the seam (provider fills the inbox; core drains it agnostically)
# --------------------------------------------------------------------------- #
def test_ingest_fills_inbox_then_apply_sets_state(store):
    register_provider("prov", lambda: FakeIngestProvider("prov", events=[{
        "kind": EVENT_EXTERNAL_IMPORTED, "ref_kind": "issue", "ref_value": "42",
        "uid": "imported-42", "state": "PLANNED", "data": {"title": "T"},
    }]))

    ing = ingest_inbox(store, discover_providers())
    assert ing.ingested == 1

    applied = apply_inbox(store)
    assert applied.applied == 1
    assert store.objects.get("imported-42").state == "PLANNED"


def test_ingest_external_state_updates_linked_object(store):
    store.objects.upsert("wi-1", "work_item", state="RED")
    store.external_refs.link("wi-1", "prov", "issue", "9")
    register_provider("prov", lambda: FakeIngestProvider("prov", events=[{
        "kind": EVENT_EXTERNAL_STATE, "ref_kind": "issue", "ref_value": "9", "state": "GREEN",
    }]))

    ingest_inbox(store, discover_providers())
    apply_inbox(store)
    assert store.objects.get("wi-1").state == "GREEN"


def test_ingest_skips_push_only_provider(store):
    register_provider("prov", lambda: FakePushProvider("prov"))  # no ingest()
    ing = ingest_inbox(store, discover_providers())
    assert ing.ingested == 0 and ing.skipped_no_ingest == 1


def test_ingest_with_no_provider_is_noop(store):
    ing = ingest_inbox(store, discover_providers())
    assert ing.providers == 0 and ing.ingested == 0


# --------------------------------------------------------------------------- #
# provider-agnostic invariant — core sync path imports no GitHub (no provider)
# --------------------------------------------------------------------------- #
def test_core_sync_path_imports_no_github():
    import atdd.state.providers as prov_mod
    import atdd.state.sync_cli as cli_mod
    import atdd.state.sync_engine as eng_mod

    for mod in (prov_mod, cli_mod, eng_mod):
        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            names += [a.name for a in getattr(node, "names", [])]
            for n in names:
                assert "github" not in n.lower(), (
                    f"{mod.__name__} imports GitHub ({n!r}); the core sync path "
                    "must stay provider-agnostic"
                )
