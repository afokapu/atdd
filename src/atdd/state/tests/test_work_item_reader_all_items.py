# URN: test:state-store:work-item-reader:all-work-items
# Issue: #1355 (#1270 slice E — migrate manifest-only readers to the store)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 slice E — ``WorkItemReader.all_work_items`` returns store-backed rows.

The store-backed analog of scanning the manifest ``sessions`` list: one
session-shaped dict per work item, with ``issue_number`` folded back in from the
GitHub external-ref (store ``data`` bags do not carry it). Fail-closed empty on
an unreadable store. New accessor — the assertion fails on the pre-slice-E reader
(no such method).
"""
from __future__ import annotations

from pathlib import Path

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.state.work_item_reader import WorkItemReader


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


def test_all_work_items_returns_session_shaped_rows_with_issue_number(tmp_path):
    _seed(tmp_path, slug="alpha", issue_number=11, status="RED", wagon="w1", train="0002")
    _seed(tmp_path, slug="beta", issue_number=22, status="GREEN", wagon="w2")
    with WorkItemReader(control_root=tmp_path) as reader:
        rows = {r["slug"]: r for r in reader.all_work_items()}
    assert set(rows) == {"alpha", "beta"}
    assert rows["alpha"]["status"] == "RED"
    assert rows["alpha"]["issue_number"] == 11  # folded in from the external-ref
    assert rows["alpha"]["wagon"] == "w1"
    assert rows["beta"]["issue_number"] == 22
    assert rows["beta"]["status"] == "GREEN"


def test_all_work_items_empty_store_returns_empty_list(tmp_path):
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    with WorkItemReader(control_root=tmp_path) as reader:
        assert reader.all_work_items() == []
