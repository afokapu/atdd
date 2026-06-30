# URN: test:coach:issue:store-authoritative-writes
# Issue: #1203 (#1168 Phase 4 cutover, Phase 2 authoritative writes)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1203 Phase 2 — `atdd issue` writes the State Store authoritatively.

Each rerouted manifest writer now writes the store first (resolved by GitHub
issue number through the external_ref), keeping the manifest mirror as a
compatibility projection. These tests assert the store actually receives the
write; they are added one writer at a time as the rerouting lands.
"""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import yaml

from atdd.coach.commands.issue import IssueManager
from atdd.state.db import connect
from atdd.state.manifest_import import GITHUB_PROVIDER
from atdd.state.store import StateStore

_MANIFEST = {
    "version": "2.0",
    "created": "2026-06-22",
    "sessions": [
        {"id": "1203", "slug": "state-store-authoritative", "issue_number": 1203,
         "type": "implementation", "status": "GREEN", "train": "0002"},
    ],
}


def _init_repo(tmp_path):
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "manifest.yaml").write_text(yaml.safe_dump(_MANIFEST), encoding="utf-8")
    return IssueManager(target_dir=tmp_path)


def _store(tmp_path):
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    return StateStore(connect(db))


def test_update_status_writes_store_authoritatively(tmp_path):
    mgr = _init_repo(tmp_path)

    mgr._update_manifest_status(1203, "SMOKE")

    # Store is authoritative: the object state reflects the new phase, resolved
    # by the github external_ref → slug.
    store = _store(tmp_path)
    ref = store.external_refs.resolve(GITHUB_PROVIDER, "issue", "1203")
    assert ref is not None
    assert store.objects.get(ref.object_uid).state == "SMOKE"


def test_update_status_unregistered_issue_is_noop_not_crash(tmp_path):
    mgr = _init_repo(tmp_path)
    # An issue with no work item / external_ref: store write is a no-op, no raise.
    assert mgr._store_set_status(999999, "SMOKE") is False


def test_update_status_still_mirrors_manifest(tmp_path):
    mgr = _init_repo(tmp_path)
    mgr._update_manifest_status(1203, "SMOKE")
    doc = yaml.safe_load((tmp_path / ".atdd" / "manifest.yaml").read_text())
    entry = next(s for s in doc["sessions"] if s["issue_number"] == 1203)
    assert entry["status"] == "SMOKE"


def test_update_fields_writes_store_authoritatively(tmp_path):
    mgr = _init_repo(tmp_path)

    mgr._update_manifest_fields(1203, {"branch": "feat/foo", "train": "0003"})

    store = _store(tmp_path)
    ref = store.external_refs.resolve(GITHUB_PROVIDER, "issue", "1203")
    obj = store.objects.get(ref.object_uid)
    assert obj.data["branch"] == "feat/foo"
    assert obj.data["train"] == "0003"
    assert obj.state == "GREEN"  # state preserved across a data merge


def test_update_fields_unregistered_issue_is_noop_not_crash(tmp_path):
    mgr = _init_repo(tmp_path)
    assert mgr._store_update_fields(999999, {"branch": "feat/x"}) is False


def test_update_fields_still_mirrors_manifest(tmp_path):
    mgr = _init_repo(tmp_path)
    mgr._update_manifest_fields(1203, {"branch": "feat/foo"})
    doc = yaml.safe_load((tmp_path / ".atdd" / "manifest.yaml").read_text())
    entry = next(s for s in doc["sessions"] if s["issue_number"] == 1203)
    assert entry["branch"] == "feat/foo"


def test_register_issue_creates_store_work_item_and_ref(tmp_path):
    mgr = _init_repo(tmp_path)

    mgr._register_issue_in_manifest(4242, "brand-new-thing", train="0009")

    store = _store(tmp_path)
    ref = store.external_refs.resolve(GITHUB_PROVIDER, "issue", "4242")
    assert ref is not None and ref.object_uid == "brand-new-thing"
    obj = store.objects.get("brand-new-thing")
    assert obj.kind == "work_item"
    assert obj.state == "INIT"
    assert obj.data["train"] == "0009"


def test_create_work_item_preserves_existing_state_on_reregister(tmp_path):
    mgr = _init_repo(tmp_path)
    # #1203 already exists at GREEN (imported from the manifest on first store touch).
    mgr._store_set_status(1203, "SMOKE")
    # Re-registering must not reset the live phase back to INIT.
    mgr._store_create_work_item(1203, "state-store-authoritative", status="INIT", data={"train": "0002"})

    store = _store(tmp_path)
    assert store.objects.get("state-store-authoritative").state == "SMOKE"


def test_create_work_item_unregistered_store_unavailable_is_false(tmp_path):
    # No .atdd at all → store cannot resolve a control root → graceful False.
    mgr = IssueManager(target_dir=tmp_path / "no-atdd-here")
    assert mgr._store_create_work_item(1, "x", status="INIT", data={}) is False


def test_archive_writes_store_complete_and_archived_date(tmp_path):
    mgr = _init_repo(tmp_path)

    # The store-authoritative portion of _archive_github: terminal phase + the
    # archived date land in the store (resolved by the github external_ref).
    mgr._store_set_status(1203, "COMPLETE")
    mgr._store_update_fields(1203, {"archived": "2026-06-30"})

    store = _store(tmp_path)
    ref = store.external_refs.resolve(GITHUB_PROVIDER, "issue", "1203")
    obj = store.objects.get(ref.object_uid)
    assert obj.state == "COMPLETE"
    assert obj.data["archived"] == "2026-06-30"


def test_archive_store_writes_are_noop_for_unregistered_issue(tmp_path):
    mgr = _init_repo(tmp_path)
    # An issue with no work item / external_ref: both store writes are graceful
    # no-ops — the GitHub close + manifest archive record still apply.
    assert mgr._store_set_status(987654, "COMPLETE") is False
    assert mgr._store_update_fields(987654, {"archived": "2026-06-30"}) is False


def test_reconcile_backfill_creates_store_work_item_and_ref(tmp_path, monkeypatch):
    mgr = _init_repo(tmp_path)

    # Fake `gh issue list` → one open atdd-issue absent from the manifest.
    gh_payload = json.dumps([
        {"number": 5151, "title": "feat(atdd): brand new reconciled thing (#5151)",
         "state": "open", "createdAt": "2026-06-30T00:00:00Z",
         "labels": [{"name": "atdd-issue"}, {"name": "atdd:RED"}]},
    ])

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=gh_payload, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    # The manifest commit is irrelevant to this assertion; tmp_path is not a git
    # repo, so make the mirror commit a no-op.
    monkeypatch.setattr(mgr, "_commit_manifest_change", lambda *a, **k: None)

    assert mgr.reconcile() == 0

    # Store is authoritative: the backfilled work item + its github external_ref
    # exist, with the phase derived from the atdd:RED label.
    store = _store(tmp_path)
    ref = store.external_refs.resolve(GITHUB_PROVIDER, "issue", "5151")
    assert ref is not None
    obj = store.objects.get(ref.object_uid)
    assert obj.kind == "work_item"
    assert obj.state == "RED"
