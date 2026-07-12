# URN: test:drive-state-machine:consolidate-worktree-command:E007-UNIT-003-existing-data-keys-preserved
# Acceptance: acc:drive-state-machine:E007-UNIT-003-existing-data-keys-preserved
# WMBT: wmbt:drive-state-machine:E007
# Phase: RED
# Harness: unit
# Layer: domain
"""E007-UNIT-003 — the binding write merges into the data bag, preserving other keys.

Issue #1347. The binding write must MERGE `branch` + `worktree_path` into the
work item's data bag, never replace it — pre-existing keys (train, wagon, …)
survive so a worktree create does not clobber the item's other metadata.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.branch import BranchManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.state.work_item_reader import WorkItemReader

pytestmark = [pytest.mark.platform]


def _control_root(tmp_path: Path) -> Path:
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return tmp_path


def test_e007_unit_003_existing_data_keys_preserved(tmp_path):
    root = _control_root(tmp_path)
    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        store.objects.upsert(
            "consolidate-worktree-cli",
            WORK_ITEM_KIND,
            state="RED",
            data={"issue_number": 1347, "train": "0002-coach-drives-lifecycle", "wagon": "drive-state-machine"},
        )
        store.external_refs.link("consolidate-worktree-cli", GITHUB_PROVIDER, "issue", "1347")
        conn.commit()
    finally:
        conn.close()

    ok = BranchManager(root)._record_binding_in_store(
        1347, "refactor/consolidate-worktree-cli", root.parent / "refactor-consolidate-worktree-cli"
    )

    assert ok is True
    with WorkItemReader(control_root=root) as reader:
        obj = reader.get(1347)
    assert obj is not None
    assert obj.data.get("branch") == "refactor/consolidate-worktree-cli"
    assert obj.data.get("worktree_path") == str(root.parent / "refactor-consolidate-worktree-cli")
    # pre-existing keys survive the merge
    assert obj.data.get("train") == "0002-coach-drives-lifecycle"
    assert obj.data.get("wagon") == "drive-state-machine"
