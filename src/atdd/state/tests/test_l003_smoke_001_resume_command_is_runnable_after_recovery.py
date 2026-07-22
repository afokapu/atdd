# URN: test:drive-state-machine:record-agent-session-identity:L003-SMOKE-001-resume-command-is-runnable-after-recovery
# Acceptance: acc:drive-state-machine:L003-SMOKE-001-resume-command-is-runnable-after-recovery
# WMBT: wmbt:drive-state-machine:L003
# Phase: SMOKE
# Harness: smoke
# Layer: integration
"""L003-SMOKE-001 — the emitted command is well-formed and needs no hand-editing.

Issue #1540. End-to-end over the REAL chokepoint and the SHIPPED provider table
(not the two-row fixture): a session is recorded by the real post-commit capture,
then the projection is rendered and the command it emits is inspected.

"Runnable" is checked structurally rather than by executing it — actually
launching an agent from a test would be an absurd side effect. What is asserted
is everything that makes it runnable: it parses as a shell command, it carries
the recorded session id and the recorded worktree, it has no unrendered
placeholders, and it survives a round-trip through the shell's own parser
(shlex), which is what catches an unquoted path with a space in it.
"""
from __future__ import annotations

import shlex

import pytest

from atdd.state.agent_session import capture_post_commit, sessions_for_work_item

from ._agent_session_helpers import SLUG, control_root, open_store, seed_work_item

pytestmark = [pytest.mark.platform]

BRANCH = "feat/record-agent-session-identity-at-write-points"
SESSION_ID = "6453e644-64cd-4254-add5-fa30135b52b1"


def test_l003_smoke_001_resume_command_is_runnable_after_recovery(tmp_path):
    root = control_root(tmp_path)
    # a path with a space — the case a naive template silently breaks on
    worktree = str(tmp_path / "my worktree")

    store = open_store(root)
    seed_work_item(store, data={"issue_number": 1540, "branch": BRANCH})
    store.conn.commit()

    # recorded through the REAL capture path, using the SHIPPED provider table
    assert capture_post_commit(
        root,
        env={"CLAUDE_CODE_SESSION_ID": SESSION_ID},
        cwd=worktree,
        branch=BRANCH,
    ) is True

    store = open_store(root)
    rows = sessions_for_work_item(store, SLUG)
    assert len(rows) == 1

    command = rows[0].resume_command
    assert command, "the projection must emit a command, not just a session id"

    assert SESSION_ID in command, "the command must name the recorded session"
    assert "{" not in command and "}" not in command, "no unrendered placeholders"

    # it must survive the shell's own parser, and the worktree must arrive as
    # ONE argument despite the space in it
    tokens = shlex.split(command)
    assert worktree in tokens, (
        f"the worktree must be a single shell token — got {tokens}"
    )
    assert SESSION_ID in tokens
