# URN: test:drive-state-machine:consolidate-worktree-command:E007-SMOKE-001-is-registered-resolves-from-store-after-create
# Acceptance: acc:drive-state-machine:E007-SMOKE-001-is-registered-resolves-from-store-after-create
# WMBT: wmbt:drive-state-machine:E007
# Phase: SMOKE
# Harness: smoke
# Layer: integration
"""E007-SMOKE-001 — after the binding write, `is-registered` resolves from the store alone.

Issue #1347. End-to-end over a real on-disk control-root State Store (tmp) with
NO .atdd/manifest.yaml: write the branch↔worktree binding via the create-path
writer, then evaluate the store-first pre-commit gate
(`IssueManager.branch_is_registered`). It must return True resolved from the
store alone — proving the #1270 pre-commit reads nothing from the manifest.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.branch import BranchManager
from atdd.coach.commands.issue import IssueManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.platform]


def test_e007_smoke_001_is_registered_resolves_from_store_after_create(tmp_path):
    root = tmp_path
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    (root / ".atdd" / "config.yaml").write_text("version: '1.0'\n")  # control-root marker, NO manifest
    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        store.objects.upsert("consolidate-worktree-cli", WORK_ITEM_KIND, state="RED", data={"issue_number": 1347})
        store.external_refs.link("consolidate-worktree-cli", GITHUB_PROVIDER, "issue", "1347")
        conn.commit()
    finally:
        conn.close()

    # Sanity: there is genuinely no manifest to fall back on.
    assert not (root / ".atdd" / "manifest.yaml").exists()

    branch = "refactor/consolidate-worktree-cli"
    assert BranchManager(root)._record_binding_in_store(
        1347, branch, root.parent / "refactor-consolidate-worktree-cli"
    ) is True

    # The store-first pre-commit gate resolves the branch from the store alone.
    assert IssueManager(root).branch_is_registered(branch) is True
