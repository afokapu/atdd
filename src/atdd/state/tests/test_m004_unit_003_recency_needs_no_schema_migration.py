# URN: test:drive-state-machine:record-agent-session-identity:M004-UNIT-003-recency-needs-no-schema-migration
# Acceptance: acc:drive-state-machine:M004-UNIT-003-recency-needs-no-schema-migration
# WMBT: wmbt:drive-state-machine:M004
# Phase: RED
# Harness: unit
# Layer: domain
"""M004-UNIT-003 — recency rides in the existing data blob; no migration.

Issue #1540, Decision 6. `external_refs.data` already exists, so recency needs
no new column and no schema version bump. This test is the regression guard on
that decision: if someone later "improves" it into a `last_seen_at` column, the
schema version moves and this goes red, forcing the migration to be a decision
rather than a side effect.
"""
from __future__ import annotations

import pytest

from atdd.state.agent_session import REF_KIND_SESSION, AgentSession, record_participation

from ._agent_session_helpers import SLUG, control_root, open_store, seed_work_item

pytestmark = [pytest.mark.platform]

SESSION = AgentSession(provider="claude", session_id="6453e644-64cd-4254-add5-fa30135b52b1")


def _schema_version(store) -> int:
    row = store.conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0])


def test_m004_unit_003_recency_needs_no_schema_migration(tmp_path):
    root = control_root(tmp_path)
    store = open_store(root)
    seed_work_item(store)
    before = _schema_version(store)

    record_participation(store, SLUG, SESSION, worktree_path="/wt", now="2026-07-18T01:00:00Z")
    store.conn.commit()

    assert _schema_version(store) == before, (
        "recency must ride in the pre-existing data blob — no migration"
    )

    # it round-trips through external_refs.data, not a column of its own
    ref = [r for r in store.external_refs.all() if r.ref_kind == REF_KIND_SESSION][0]
    assert ref.data.get("last_seen_at") == "2026-07-18T01:00:00Z"

    columns = {r[1] for r in store.conn.execute("PRAGMA table_info(external_refs)")}
    assert "last_seen_at" not in columns, "recency must not have become a column"
    assert columns == {"id", "object_uid", "provider", "ref_kind", "ref_value", "data", "created_at"}
