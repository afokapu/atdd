# URN: test:drive-state-machine:record-agent-session-identity:E010-UNIT-002-second-commit-adds-no-new-row
# Acceptance: acc:drive-state-machine:E010-UNIT-002-second-commit-adds-no-new-row
# WMBT: wmbt:drive-state-machine:E010
# Phase: RED
# Harness: unit
# Layer: application
"""E010-UNIT-002 — participation is idempotent per (session, work_item).

Issue #1540. Agents commit constantly; a row per commit would turn the store
into an activity log, which #1540 explicitly refuses (exactly one recency value
per session, no history). The relationships table is UNIQUE
(src_uid, dst_uid, rel_type), so this holds structurally — this test pins that
the capture path actually relies on it rather than inserting blindly.
"""
from __future__ import annotations

import pytest

from atdd.state.agent_session import (
    REF_KIND_SESSION,
    REL_SESSION_PARTICIPATES_IN_WORK_ITEM,
    capture_post_commit,
)

from ._agent_session_helpers import SLUG, control_root, open_store, seed_work_item

pytestmark = [pytest.mark.platform]

BRANCH = "feat/record-agent-session-identity-at-write-points"
SESSION_ID = "6453e644-64cd-4254-add5-fa30135b52b1"


def _commit_once(root, worktree):
    return capture_post_commit(
        root,
        env={"CLAUDE_CODE_SESSION_ID": SESSION_ID},
        cwd=worktree,
        branch=BRANCH,
    )


def test_e010_unit_002_second_commit_adds_no_new_row(tmp_path):
    root = control_root(tmp_path)
    worktree = str(tmp_path / "wt")

    store = open_store(root)
    seed_work_item(store, data={"issue_number": 1540, "branch": BRANCH})
    store.conn.commit()

    assert _commit_once(root, worktree) is True
    assert _commit_once(root, worktree) is True
    assert _commit_once(root, worktree) is True

    store = open_store(root)
    refs = [r for r in store.external_refs.all() if r.ref_kind == REF_KIND_SESSION]
    assert len(refs) == 1, f"three commits, one session — got {len(refs)} session refs"

    rels = [r for r in store.relationships.list(dst_uid=SLUG)
            if r.rel_type == REL_SESSION_PARTICIPATES_IN_WORK_ITEM]
    assert len(rels) == 1, f"three commits, one participation — got {len(rels)} rows"
