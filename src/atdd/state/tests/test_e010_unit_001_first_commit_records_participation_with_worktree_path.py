# URN: test:drive-state-machine:record-agent-session-identity:E010-UNIT-001-first-commit-records-participation-with-worktree-path
# Acceptance: acc:drive-state-machine:E010-UNIT-001-first-commit-records-participation-with-worktree-path
# WMBT: wmbt:drive-state-machine:E010
# Phase: RED
# Harness: unit
# Layer: application
"""E010-UNIT-001 — a commit records the session against its branch's work_item.

Issue #1540. Committing is the one act every agent performs on work it touches,
so post-commit is the second mandatory chokepoint. Branch → work_item resolution
reuses the E007 seam (the binding already written at worktree create).

The worktree path is the load-bearing field: because no role is stored, it is
the ONLY thing that later makes orchestrator-vs-worker inferable — a session
participating solely in the worktree matching its own launch cwd behaves as a
worker; one participating across many behaves as an orchestrator.
"""
from __future__ import annotations

import pytest

from atdd.state.agent_session import (
    KIND_AGENT_SESSION,
    REF_KIND_SESSION,
    REL_SESSION_PARTICIPATES_IN_WORK_ITEM,
    capture_post_commit,
)

from ._agent_session_helpers import SLUG, control_root, open_store, seed_work_item

pytestmark = [pytest.mark.platform]

BRANCH = "feat/record-agent-session-identity-at-write-points"
SESSION_ID = "6453e644-64cd-4254-add5-fa30135b52b1"


def test_e010_unit_001_first_commit_records_participation_with_worktree_path(tmp_path):
    root = control_root(tmp_path)
    worktree = str(tmp_path / "feat-record-agent-session-identity")

    store = open_store(root)
    seed_work_item(store, data={"issue_number": 1540, "branch": BRANCH})
    store.conn.commit()

    ok = capture_post_commit(
        root,
        env={"CLAUDE_CODE_SESSION_ID": SESSION_ID},
        cwd=worktree,
        branch=BRANCH,
    )

    assert ok is True

    store = open_store(root)
    refs = [r for r in store.external_refs.all() if r.ref_kind == REF_KIND_SESSION]
    assert len(refs) == 1
    assert refs[0].provider == "claude"
    assert refs[0].ref_value == SESSION_ID

    session_uid = refs[0].object_uid
    assert store.objects.get(session_uid).kind == KIND_AGENT_SESSION

    rels = [r for r in store.relationships.list(src_uid=session_uid)
            if r.rel_type == REL_SESSION_PARTICIPATES_IN_WORK_ITEM]
    assert len(rels) == 1
    assert rels[0].dst_uid == SLUG
    assert rels[0].data.get("worktree_path") == worktree, (
        "participation must carry the worktree it was captured in — "
        "without it, role inference has nothing to work from"
    )
    # and still no role
    assert "role" not in {k.lower() for k in rels[0].data}
