# URN: test:state-store:work-item-reader:cli-accessor
# Issue: #1320 (#1270 slice B — decommission the manifest mirror)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 slice B — WorkItemReader accessor extensions for the CLI readers.

Adds feature(), issue_number_for_slug(), session_entry() consumed by the
pr/branch/issue_lifecycle/sync_wmbts repoints. Isolated tmp-store tests
(explicit db_path), independent of the ambient control-root layout.
"""
from __future__ import annotations

import yaml
import pytest

from atdd.state.work_item_reader import WorkItemReader

_MANIFEST = {
    "version": "2.0",
    "sessions": [
        {"id": "1203", "slug": "state-store-authoritative", "issue_number": 1203,
         "type": "implementation", "status": "PLANNED", "train": "0002",
         "branch": "feat/ssa", "feature": "feature:atdd:state-store",
         "wagon": "govern-lifecycle", "created": "2026-06-01", "archived": None},
        {"id": "900", "slug": "older-thing", "issue_number": 900, "type": "refactor",
         "status": "COMPLETE", "train": "0001", "branch": "fix/older"},
    ],
}


@pytest.fixture()
def reader(tmp_path):
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "manifest.yaml").write_text(yaml.safe_dump(_MANIFEST), encoding="utf-8")
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    with WorkItemReader(control_root=tmp_path, db_path=db) as r:
        yield r


def test_feature_reads_from_store(reader):
    assert reader.feature(1203) == "feature:atdd:state-store"
    assert reader.feature(900) is None          # no feature recorded
    assert reader.feature(424242) is None        # unregistered


def test_issue_number_for_slug(reader):
    assert reader.issue_number_for_slug("state-store-authoritative") == 1203
    assert reader.issue_number_for_slug("older-thing") == 900
    assert reader.issue_number_for_slug("nope") is None


def test_session_entry_reconstructs_manifest_shape(reader):
    entry = reader.session_entry(1203)
    assert entry is not None
    assert entry["slug"] == "state-store-authoritative"   # from uid
    assert entry["status"] == "PLANNED"                    # from state
    assert entry["type"] == "implementation"               # from data
    assert entry["train"] == "0002"
    assert reader.session_entry(424242) is None
