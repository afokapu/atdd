# URN: test:drive-state-machine:record-agent-session-identity:M004-UNIT-001-sessions-order-by-last-seen-at
# Acceptance: acc:drive-state-machine:M004-UNIT-001-sessions-order-by-last-seen-at
# WMBT: wmbt:drive-state-machine:M004
# Phase: RED
# Harness: unit
# Layer: domain
"""M004-UNIT-001 — sessions order by last_seen_at, not by creation order.

Issue #1540. Measured on the live machine: 68 of 304 projects carry more than
one chat, and across those, created-order and last-activity-order DIVERGE IN 22
(32%). So creation order is not a proxy for "which session should I resume" —
it is wrong about a third of the time.

The fixture is built to be adversarial about exactly that: the session created
FIRST is seen LAST, so any implementation that quietly falls back to insertion
order or rowid ranks it wrongly and this test catches it. An ordering test whose
two orders happen to agree proves nothing.
"""
from __future__ import annotations

import pytest

from atdd.state.agent_session import AgentSession, record_participation, sessions_for_work_item

from ._agent_session_helpers import SLUG, control_root, open_store, seed_work_item

pytestmark = [pytest.mark.platform]

OLD = AgentSession(provider="claude", session_id="aaaa-oldest-created")
MID = AgentSession(provider="claude", session_id="bbbb-middle")
NEW = AgentSession(provider="claude", session_id="cccc-newest-created")


def test_m004_unit_001_sessions_order_by_last_seen_at(tmp_path):
    root = control_root(tmp_path)
    store = open_store(root)
    seed_work_item(store)

    # creation order: OLD, MID, NEW
    record_participation(store, SLUG, OLD, worktree_path="/wt/a", now="2026-07-18T01:00:00Z")
    record_participation(store, SLUG, MID, worktree_path="/wt/b", now="2026-07-18T02:00:00Z")
    record_participation(store, SLUG, NEW, worktree_path="/wt/c", now="2026-07-18T03:00:00Z")

    # ...then the OLDEST-created session acts again, most recently of all.
    record_participation(store, SLUG, OLD, worktree_path="/wt/a", now="2026-07-18T09:00:00Z")
    store.conn.commit()

    rows = sessions_for_work_item(store, SLUG)

    assert [r.session.session_id for r in rows] == [
        OLD.session_id,  # last seen 09:00 — first created, yet ranks first
        NEW.session_id,  # 03:00
        MID.session_id,  # 02:00
    ], "sessions must rank by last_seen_at, not by when the row was created"

    seen = [r.last_seen_at for r in rows]
    assert seen == sorted(seen, reverse=True)
