# URN: test:drive-state-machine:record-agent-session-identity:E010-UNIT-004-creator-committing-alone-is-both-without-inventing-a-role
# Acceptance: acc:drive-state-machine:E010-UNIT-004-creator-committing-alone-is-both-without-inventing-a-role
# WMBT: wmbt:drive-state-machine:E010
# Phase: RED
# Harness: unit
# Layer: application
"""E010-UNIT-004 — one session can be creator AND participant; still no role.

Issue #1540, Decision 5. This is the case that most tempts a role field: a lone
session that filed the issue and did all the work "obviously" is the worker.

It is not obviously anything. The documented recovery procedure has an
orchestrator commit inside a worker's worktree, so committing proves
participation and nothing more. Two neutral edges are recorded and the
interpretation is left to the reader — which is what makes the record survive
being wrong about roles.
"""
from __future__ import annotations

import pytest

from atdd.state.agent_session import (
    REF_KIND_SESSION,
    REL_SESSION_CREATED_WORK_ITEM,
    REL_SESSION_PARTICIPATES_IN_WORK_ITEM,
    AgentSession,
    capture_post_commit,
    record_creator,
)

from ._agent_session_helpers import SLUG, control_root, open_store, seed_work_item

pytestmark = [pytest.mark.platform]

BRANCH = "feat/record-agent-session-identity-at-write-points"
SESSION_ID = "6453e644-64cd-4254-add5-fa30135b52b1"

ROLE_WORDS = {"role", "roles", "orchestrator", "worker", "is_worker", "is_orchestrator"}


def test_e010_unit_004_creator_committing_alone_is_both_without_inventing_a_role(tmp_path):
    root = control_root(tmp_path)
    store = open_store(root)
    seed_work_item(store, data={"issue_number": 1540, "branch": BRANCH})

    session = AgentSession(provider="claude", session_id=SESSION_ID)
    assert record_creator(store, SLUG, session) is True
    store.conn.commit()

    assert capture_post_commit(
        root, env={"CLAUDE_CODE_SESSION_ID": SESSION_ID},
        cwd=str(tmp_path / "wt"), branch=BRANCH,
    ) is True

    store = open_store(root)
    refs = [r for r in store.external_refs.all() if r.ref_kind == REF_KIND_SESSION]
    assert len(refs) == 1, "one session, one ref — creator and participant are the same identity"
    session_uid = refs[0].object_uid

    rel_types = {r.rel_type for r in store.relationships.list(src_uid=session_uid)}
    assert REL_SESSION_CREATED_WORK_ITEM in rel_types
    assert REL_SESSION_PARTICIPATES_IN_WORK_ITEM in rel_types

    # nothing anywhere may name a role
    blobs = [refs[0].data or {}]
    blobs += [r.data or {} for r in store.relationships.list(src_uid=session_uid)]
    blobs += [o.data or {} for o in (store.objects.get(session_uid), store.objects.get(SLUG)) if o]
    for blob in blobs:
        assert not {k.lower() for k in blob} & ROLE_WORDS, f"a role was invented: {blob}"
