# URN: test:drive-state-machine:record-agent-session-identity:L003-UNIT-001-projection-emits-runnable-resume-command
# Acceptance: acc:drive-state-machine:L003-UNIT-001-projection-emits-runnable-resume-command
# WMBT: wmbt:drive-state-machine:L003
# Phase: RED
# Harness: unit
# Layer: application
"""L003-UNIT-001 — the projection emits a runnable resume command per session.

Issue #1540. This is the payoff: after a crash, an orchestrator reads the store
and gets, per work_item, the literal command to re-enter each session.

"Runnable" is the whole point and is asserted as such — a projection that emits
a session id and leaves the operator to reconstruct the invocation has moved the
work rather than done it. Both the id and the cwd must be present, because
resuming in the wrong directory resumes the wrong context.

The command is rendered from the provider's own `resume_template`, so core
hardcodes no vendor's CLI.
"""
from __future__ import annotations

import pytest

from atdd.state import agent_session
from atdd.state.agent_session import AgentSession, record_participation, sessions_for_work_item

from ._agent_session_helpers import (
    SLUG,
    control_root,
    open_store,
    seed_work_item,
    write_provider_table,
)

pytestmark = [pytest.mark.platform]

A = AgentSession(provider="claude", session_id="aaaa-1111")
B = AgentSession(provider="other", session_id="bbbb-2222")


def test_l003_unit_001_projection_emits_runnable_resume_command(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_session, "PROVIDER_TABLE_PATH", write_provider_table(tmp_path))
    agent_session.load_provider_table.cache_clear()

    root = control_root(tmp_path)
    store = open_store(root)
    seed_work_item(store)
    record_participation(store, SLUG, A, worktree_path="/wt/alpha", now="2026-07-18T02:00:00Z")
    record_participation(store, SLUG, B, worktree_path="/wt/beta", now="2026-07-18T05:00:00Z")
    store.conn.commit()

    rows = sessions_for_work_item(store, SLUG)

    assert len(rows) == 2
    assert [r.session.session_id for r in rows] == ["bbbb-2222", "aaaa-1111"]

    by_id = {r.session.session_id: r for r in rows}
    # each provider's command comes from its own table row
    assert by_id["aaaa-1111"].resume_command == "cd /wt/alpha && claude --resume aaaa-1111"
    assert by_id["bbbb-2222"].resume_command == "other-cli attach bbbb-2222 --dir /wt/beta"

    for row in rows:
        assert row.session.session_id in row.resume_command, "the command must name the session"
        assert row.worktree_path in row.resume_command, "the command must name the cwd"
        assert "{" not in row.resume_command, "template placeholders must be rendered, not emitted"


def test_l003_unit_001_projection_asserts_no_role(tmp_path, monkeypatch):
    """Roles are inferred by the reader; the projection states facts only."""
    monkeypatch.setattr(agent_session, "PROVIDER_TABLE_PATH", write_provider_table(tmp_path))
    agent_session.load_provider_table.cache_clear()

    root = control_root(tmp_path)
    store = open_store(root)
    seed_work_item(store)
    record_participation(store, SLUG, A, worktree_path="/wt/alpha", now="2026-07-18T02:00:00Z")
    store.conn.commit()

    row = sessions_for_work_item(store, SLUG)[0]

    assert not hasattr(row, "role")
    fields = {f.lower() for f in row.__dataclass_fields__}
    assert not fields & {"role", "orchestrator", "worker", "is_worker"}
