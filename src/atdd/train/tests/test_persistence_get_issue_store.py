# URN: test:drive-state-machine:train-persistence:get-issue-store-only
# Issue: #1355 (#1270 slice E — migrate manifest-only readers to the store)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 slice E — ``JsonlPersistenceStore.get_issue`` reads the State Store.

The train machinery's issue-record read was manifest-only; slice E repoints it
at the State Store (authoritative since #1203), folding ``issue_number`` back in
from the GitHub external-ref. Discriminator: with a store-seeded item and NO
manifest, the record resolves — the old manifest-only read raised ``KeyError``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.train.persistence import JsonlPersistenceStore


def _seed(root: Path, *, slug: str, issue_number: int, status: str, **data) -> None:
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    (root / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    db = init_state_store(start=root)
    conn = connect(db)
    try:
        s = StateStore(conn)
        s.objects.upsert(slug, WORK_ITEM_KIND, state=status, data=dict(data))
        s.external_refs.link(slug, GITHUB_PROVIDER, "issue", str(issue_number), data={})
    finally:
        conn.close()


def test_get_issue_reads_record_from_store_without_manifest(tmp_path):
    _seed(tmp_path, slug="my-item", issue_number=500, status="GREEN",
          type="refactor", train="0002-coach-drives-lifecycle")
    rec = JsonlPersistenceStore(repo_root=tmp_path).get_issue(500)
    assert rec.issue_number == 500
    assert rec.slug == "my-item"
    assert rec.status.value == "GREEN"
    assert rec.train == "0002-coach-drives-lifecycle"
    assert rec.type.value == "refactor"


def test_get_issue_unregistered_raises_keyerror(tmp_path):
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    with pytest.raises(KeyError):
        JsonlPersistenceStore(repo_root=tmp_path).get_issue(999)
