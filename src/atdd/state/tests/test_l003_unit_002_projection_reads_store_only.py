# URN: test:drive-state-machine:record-agent-session-identity:L003-UNIT-002-projection-reads-store-only
# Acceptance: acc:drive-state-machine:L003-UNIT-002-projection-reads-store-only
# WMBT: wmbt:drive-state-machine:L003
# Phase: RED
# Harness: unit
# Layer: application
"""L003-UNIT-002 — the projection resolves from the store alone.

Issue #1540. The failure this feature exists to fix is recovery depending on a
multiplexer's own session file — a single-provider artifact with one rollback
slot, that takes everything with it when lost. A projection that reads that
file to render itself would rebuild the same dependency at the read end.

So the environment here is hostile on purpose: PATH is emptied, so ANY attempt
to exec a helper binary fails rather than silently succeeding on a dev machine
where it happens to be installed. Passing under those conditions is what makes
"store alone" a measurement rather than a claim.
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

SESSION = AgentSession(provider="claude", session_id="6453e644-64cd-4254-add5-fa30135b52b1")


def test_l003_unit_002_projection_reads_store_only(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_session, "PROVIDER_TABLE_PATH", write_provider_table(tmp_path))
    agent_session.load_provider_table.cache_clear()

    root = control_root(tmp_path)
    store = open_store(root)
    seed_work_item(store)
    record_participation(store, SLUG, SESSION, worktree_path="/wt", now="2026-07-18T02:00:00Z")
    store.conn.commit()

    # nothing external is reachable: no PATH, no HOME to hide a session file in
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))

    def _no_subprocess(*args, **kwargs):
        raise AssertionError("the projection shelled out; it must read the store alone")

    monkeypatch.setattr("subprocess.run", _no_subprocess)
    monkeypatch.setattr("subprocess.Popen", _no_subprocess)
    monkeypatch.setattr("subprocess.check_output", _no_subprocess)

    rows = sessions_for_work_item(store, SLUG)

    assert len(rows) == 1
    assert rows[0].session.session_id == SESSION.session_id
    assert rows[0].resume_command == (
        "cd /wt && claude --resume 6453e644-64cd-4254-add5-fa30135b52b1"
    )
