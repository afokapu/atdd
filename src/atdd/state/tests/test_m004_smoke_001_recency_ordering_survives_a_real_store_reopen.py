# URN: test:drive-state-machine:record-agent-session-identity:M004-SMOKE-001-recency-ordering-survives-a-real-store-reopen
# Acceptance: acc:drive-state-machine:M004-SMOKE-001-recency-ordering-survives-a-real-store-reopen
# WMBT: wmbt:drive-state-machine:M004
# Phase: SMOKE
# Harness: smoke
# Layer: integration
"""M004-SMOKE-001 — recency ordering survives the process that wrote it.

Issue #1540. Durability is the whole premise: the reader is an orchestrator that
crashed, so the process which recorded the sessions is by definition gone. An
ordering that only holds in the writing process's memory would be useless
exactly when it is needed.

So this writes through a real on-disk store, then reads it back from a SEPARATE
process — the only way to distinguish "persisted" from "still in this
connection".
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from atdd.state.agent_session import AgentSession, record_participation

from ._agent_session_helpers import SLUG, control_root, open_store, seed_work_item

pytestmark = [pytest.mark.platform]

READBACK = """
import sys
from pathlib import Path
from atdd.state.agent_session import sessions_for_work_item
from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore

root = Path(sys.argv[1])
store = StateStore(connect(init_state_store(start=root)))
rows = sessions_for_work_item(store, sys.argv[2])
print(",".join(r.session.session_id for r in rows))
"""


def test_m004_smoke_001_recency_ordering_survives_a_real_store_reopen(tmp_path):
    root = control_root(tmp_path)
    store = open_store(root)
    seed_work_item(store)

    # created oldest-first, but seen in the opposite order
    record_participation(store, SLUG, AgentSession("claude", "first-created"),
                         worktree_path="/wt/a", now="2026-07-18T01:00:00Z")
    record_participation(store, SLUG, AgentSession("claude", "second-created"),
                         worktree_path="/wt/b", now="2026-07-18T02:00:00Z")
    record_participation(store, SLUG, AgentSession("claude", "first-created"),
                         worktree_path="/wt/a", now="2026-07-18T09:00:00Z")
    store.conn.commit()
    store.conn.close()  # the writing process is gone

    proc = subprocess.run(
        [sys.executable, "-c", READBACK, str(root), SLUG],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr

    order = proc.stdout.strip().split(",")
    assert order == ["first-created", "second-created"], (
        "recency ordering must survive the reopen — recovery reads a store whose "
        f"writer has crashed; got {order}"
    )
