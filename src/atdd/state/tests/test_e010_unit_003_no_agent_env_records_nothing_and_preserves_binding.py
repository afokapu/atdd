# URN: test:drive-state-machine:record-agent-session-identity:E010-UNIT-003-no-agent-env-records-nothing-and-preserves-binding
# Acceptance: acc:drive-state-machine:E010-UNIT-003-no-agent-env-records-nothing-and-preserves-binding
# WMBT: wmbt:drive-state-machine:E010
# Phase: RED
# Harness: unit
# Layer: application
"""E010-UNIT-003 — a human commit records nothing and destroys nothing.

Issue #1540. The dangerous half of "no-op" is the second half. It is easy to
write capture that, finding no session, clears the field it would have written —
so an operator's `git commit` on a worker's branch silently erases the worker's
binding, and recovery loses the very session it needed.

Capture may only ever ADD what it observed. It must never null out what it
could not observe.
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
WORKER_SESSION = "6453e644-64cd-4254-add5-fa30135b52b1"


def test_e010_unit_003_no_agent_env_records_nothing_and_preserves_binding(tmp_path):
    root = control_root(tmp_path)
    worktree = str(tmp_path / "wt")

    store = open_store(root)
    seed_work_item(store, data={"issue_number": 1540, "branch": BRANCH})
    store.conn.commit()

    # a worker committed first
    assert capture_post_commit(
        root, env={"CLAUDE_CODE_SESSION_ID": WORKER_SESSION},
        cwd=worktree, branch=BRANCH,
    ) is True

    store = open_store(root)
    before = [r for r in store.external_refs.all() if r.ref_kind == REF_KIND_SESSION]
    assert len(before) == 1
    before_seen = before[0].data.get("last_seen_at")

    # now a HUMAN commits on the same branch — no agent env var at all
    result = capture_post_commit(root, env={"HOME": "/tmp"}, cwd=worktree, branch=BRANCH)

    assert result is False, "no session observed — capture must report it did nothing"

    store = open_store(root)
    after = [r for r in store.external_refs.all() if r.ref_kind == REF_KIND_SESSION]
    assert len(after) == 1, "the human commit must not add a session"
    assert after[0].ref_value == WORKER_SESSION, "the worker's binding must survive"
    assert after[0].data.get("last_seen_at") == before_seen, (
        "a human commit must not touch the worker's recency — it observed nothing"
    )

    rels = [r for r in store.relationships.list(dst_uid=SLUG)
            if r.rel_type == REL_SESSION_PARTICIPATES_IN_WORK_ITEM]
    assert len(rels) == 1, "the worker's participation must survive a human commit"
