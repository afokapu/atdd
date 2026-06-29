# URN: test:state-store:work-item-reader:store-vs-manifest-equivalence
# Issue: #1203 (#1168 Phase 4 cutover)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1203 Phase 1 — store-backed work-item reader (shadow reads).

The State Store becomes the read source for `atdd issue` work-item state. These
tests prove the reader:

- reproduces what the manifest carries (status/train/branch keyed by the GitHub
  issue number) — the GT-301 store-vs-manifest equivalence gate;
- auto-imports the manifest into the store on first read when the store is empty
  (Decision #3 — reuse the single #1183 import path);
- reads from the **store**, not by re-parsing the YAML (a store mutation is
  reflected without rewriting the manifest);
- returns ``None`` for an issue that is not registered (an unregistered issue is
  valid and must not crash the lifecycle).
"""
from __future__ import annotations

import pytest
import yaml

from atdd.state.db import connect
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.state.work_item_reader import WorkItemReader

_MANIFEST = {
    "version": "2.0",
    "sessions": [
        {
            "id": "1203",
            "slug": "state-store-authoritative",
            "issue_number": 1203,
            "type": "implementation",
            "status": "PLANNED",
            "train": "0002",
            "branch": "feat/state-store-authoritative-work-item-lifecycle",
            "feature": "feature:atdd:state-store",
        },
        {
            "id": "900",
            "slug": "older-thing",
            "issue_number": 900,
            "type": "refactor",
            "status": "COMPLETE",
            "train": "0001",
            "branch": "fix/older",
        },
    ],
}


def _write_manifest(root, doc=None):
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    path = root / ".atdd" / "manifest.yaml"
    path.write_text(yaml.safe_dump(doc if doc is not None else _MANIFEST), encoding="utf-8")
    return path


def _manifest_lookup(doc, issue_number):
    """The pre-cutover manifest read (session matched by issue_number)."""
    for entry in doc.get("sessions") or []:
        if entry.get("issue_number") == issue_number:
            return entry.get("status"), entry.get("train"), entry.get("branch")
    return None, None, None


@pytest.fixture()
def reader(tmp_path):
    _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    with WorkItemReader(control_root=tmp_path, db_path=db) as r:
        yield r


def test_status_train_branch_match_manifest(reader):
    assert reader.status(1203) == "PLANNED"
    assert reader.train(1203) == "0002"
    assert reader.branch(1203) == "feat/state-store-authoritative-work-item-lifecycle"

    assert reader.status(900) == "COMPLETE"
    assert reader.train(900) == "0001"
    assert reader.branch(900) == "fix/older"


def test_store_vs_manifest_equivalence(reader):
    """GT-301: every registered issue reads identically from store and manifest."""
    for entry in _MANIFEST["sessions"]:
        n = entry["issue_number"]
        expected = _manifest_lookup(_MANIFEST, n)
        got = (reader.status(n), reader.train(n), reader.branch(n))
        assert got == expected, f"issue #{n}: store {got} != manifest {expected}"


def test_empty_store_auto_imports_on_first_read(tmp_path):
    """A fresh, un-imported store is populated from the manifest on first read."""
    _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    # No explicit import_manifest call — the reader must do it.
    with WorkItemReader(control_root=tmp_path, db_path=db) as r:
        assert r.status(1203) == "PLANNED"

    # The store now actually holds the work items (not re-read from YAML each time).
    conn = connect(db)
    try:
        store = StateStore(conn)
        assert {o.uid for o in store.objects.list(kind=WORK_ITEM_KIND)} == {
            "state-store-authoritative",
            "older-thing",
        }
        assert store.external_refs.resolve(GITHUB_PROVIDER, "issue", "1203") is not None
    finally:
        conn.close()


def test_reads_from_store_not_yaml(reader, tmp_path):
    """A store-only mutation is visible to the reader without touching the manifest."""
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    conn = connect(db)
    try:
        StateStore(conn).objects.set_state("state-store-authoritative", "RED")
    finally:
        conn.close()
    assert reader.status(1203) == "RED"  # store wins; manifest still says PLANNED


def test_unregistered_issue_returns_none(reader):
    assert reader.status(424242) is None
    assert reader.train(424242) is None
    assert reader.branch(424242) is None


def test_missing_manifest_yields_empty_reads(tmp_path):
    """No manifest and an empty store: reads are None, not a crash."""
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    with WorkItemReader(control_root=tmp_path, db_path=db) as r:
        assert r.status(1203) is None
        assert r.train(1203) is None
        assert r.branch(1203) is None
