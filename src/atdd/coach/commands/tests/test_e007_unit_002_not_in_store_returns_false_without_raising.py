# URN: test:drive-state-machine:consolidate-worktree-command:E007-UNIT-002-not-in-store-returns-false-without-raising
# Acceptance: acc:drive-state-machine:E007-UNIT-002-not-in-store-returns-false-without-raising
# WMBT: wmbt:drive-state-machine:E007
# Phase: RED
# Harness: unit
# Layer: domain
"""E007-UNIT-002 — binding write is a no-raise no-op when the issue is not in the store.

Issue #1347. When the work item / github external_ref for the issue is absent,
`_record_binding_in_store` returns False, raises nothing, and creates no work
item (it must never fabricate a work item as a side effect of worktree creation).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.branch import BranchManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.platform]


def _control_root(tmp_path: Path) -> Path:
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return tmp_path


def test_e007_unit_002_not_in_store_returns_false_without_raising(tmp_path):
    root = _control_root(tmp_path)
    # Initialise an empty store (no work item, no external_ref for 1347).
    init_state_store(start=root)

    ok = BranchManager(root)._record_binding_in_store(
        1347, "refactor/consolidate-worktree-cli", root.parent / "refactor-consolidate-worktree-cli"
    )

    assert ok is False
    conn = connect(init_state_store(start=root))
    try:
        assert StateStore(conn).objects.list(kind=WORK_ITEM_KIND) == []
    finally:
        conn.close()
