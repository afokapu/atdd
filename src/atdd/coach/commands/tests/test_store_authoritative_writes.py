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
