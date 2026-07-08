# URN: test:drive-state-machine:consolidate-worktree-command:E007-UNIT-001-create-writes-branch-and-worktree-path-to-store
# Acceptance: acc:drive-state-machine:E007-UNIT-001-create-writes-branch-and-worktree-path-to-store
# WMBT: wmbt:drive-state-machine:E007
# Phase: RED
# Harness: unit
# Layer: domain
"""E007-UNIT-001 — the create path writes data.branch + data.worktree_path to the store.

Issue #1347. `BranchManager._record_binding_in_store` is the single writer of the
branch↔issue↔worktree binding into the control-root State Store — the seam the
#1270 pre-commit gate (`atdd issue is-registered`, store-first) resolves once the
manifest mirror is gone. It resolves issue_number → work item via the github
external_ref and merges `branch` + `worktree_path` into the object's data bag,
preserving kind + lifecycle state, with zero commits to local main.
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
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")  # control-root marker
    return tmp_path


def _seed(root: Path, slug: str, issue_number: int, data=None) -> None:
    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        store.objects.upsert(
            slug, WORK_ITEM_KIND, state="RED", data=data or {"issue_number": issue_number}
        )
        store.external_refs.link(slug, GITHUB_PROVIDER, "issue", str(issue_number))
        conn.commit()
    finally:
        conn.close()


def test_e007_unit_001_create_writes_branch_and_worktree_path_to_store(tmp_path):
    root = _control_root(tmp_path)
    _seed(root, "consolidate-worktree-cli", 1347)
    worktree_path = root.parent / "refactor-consolidate-worktree-cli"

    ok = BranchManager(root)._record_binding_in_store(
        1347, "refactor/consolidate-worktree-cli", worktree_path
    )

    assert ok is True
    with WorkItemReader(control_root=root) as reader:
        obj = reader.get(1347)
    assert obj is not None
    assert obj.data.get("branch") == "refactor/consolidate-worktree-cli"
    assert obj.data.get("worktree_path") == str(worktree_path)
    # kind + lifecycle state are untouched by a binding write
    assert obj.kind == WORK_ITEM_KIND
    assert obj.state == "RED"
