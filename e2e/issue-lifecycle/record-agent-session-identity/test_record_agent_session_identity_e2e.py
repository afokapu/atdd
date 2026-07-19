# URN: test:train:issue-lifecycle:record-agent-session-identity:E2E-001-both-chokepoints-end-to-end
# Train: train:issue-lifecycle:record-agent-session-identity
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Assertion: behavioral
# Purpose: E2E for the whole train — a session is recorded at BOTH chokepoints
#          against a real store and a real git repo, and the projection then
#          hands back a runnable resume command with no multiplexer present.
"""End-to-end for train:issue-lifecycle:record-agent-session-identity.

Walks the train's five steps as one story, which is the thing no unit test can
assert: provider table -> creator at mint -> participant at post-commit ->
recency -> resume projection.

The scenario is the one the train exists for: an orchestrator crashes, and has
to re-enter the fleet from the store alone. Two sessions touch one work_item,
the second more recently; recovery must name the right one and hand back a
command that runs.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from atdd.state.agent_session import (
    AgentSession,
    capture_post_commit,
    record_creator,
    sessions_for_work_item,
)
from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore

pytestmark = [pytest.mark.platform]

SLUG = "record-agent-session-identity-at-write-points"
BRANCH = "feat/record-agent-session-identity-at-write-points"
ORCHESTRATOR = "1111aaaa-orchestrator"
WORKER = "2222bbbb-worker"


def _store(root: Path) -> StateStore:
    return StateStore(connect(init_state_store(start=root)))


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "worker-worktree"
    repo.mkdir()
    for args in (("init", "-q", "-b", BRANCH),
                 ("config", "user.email", "t@example.com"),
                 ("config", "user.name", "T")):
        subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    return repo


def test_record_agent_session_identity_e2e(tmp_path):
    root = tmp_path / "control"
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text("version: '1.0'\n")

    store = _store(root)
    store.objects.upsert(SLUG, "work_item", state="RED",
                         data={"issue_number": 1540, "branch": BRANCH})
    store.external_refs.link(SLUG, "github", "issue", "1540")

    # step 2 — the orchestrator filed the issue
    assert record_creator(
        store, SLUG, AgentSession("claude", ORCHESTRATOR), now="2026-07-18T01:00:00Z"
    ) is True
    store.conn.commit()

    # step 3 — a worker then commits in its own worktree
    repo = _repo(tmp_path)
    assert capture_post_commit(
        root, env={"CLAUDE_CODE_SESSION_ID": WORKER},
        cwd=str(repo), branch=BRANCH,
    ) is True

    # step 4 — the orchestrator commits too, later, in the WORKER's worktree.
    # This is the documented recovery procedure, and the exact reason no role
    # is stored: participation here does not make the orchestrator a worker.
    assert capture_post_commit(
        root, env={"CLAUDE_CODE_SESSION_ID": ORCHESTRATOR},
        cwd=str(repo), branch=BRANCH,
    ) is True

    # step 5 — recovery reads the store alone
    rows = sessions_for_work_item(_store(root), SLUG)

    assert len(rows) == 2
    assert rows[0].session.session_id == ORCHESTRATOR, "most recently seen ranks first"

    by_id = {r.session.session_id: r for r in rows}
    assert by_id[ORCHESTRATOR].created is True
    assert by_id[WORKER].created is False
    for row in rows:
        assert row.worktree_path == str(repo)
        assert row.resume_command
        assert row.session.session_id in row.resume_command
        assert "{" not in row.resume_command

    # the whole point: no role was ever written, so nothing had to be right
    # about who was the worker.
    for row in rows:
        assert not {f.lower() for f in row.__dataclass_fields__} & {
            "role", "orchestrator", "worker"
        }
