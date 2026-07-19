# URN: test:drive-state-machine:record-agent-session-identity:E009-UNIT-001-mint-records-creating-session
# Acceptance: acc:drive-state-machine:E009-UNIT-001-mint-records-creating-session
# WMBT: wmbt:drive-state-machine:E009
# Phase: RED
# Harness: unit
# Layer: application
"""E009-UNIT-001 — `atdd author issue` records the creating session.

Issue #1540. The mint is a mandatory chokepoint: every work_item passes through
it exactly once, so it is where the CREATOR is captured — from ambient env via
the provider table, never by asking the agent.

Asserted against the REAL command rather than the recorder in isolation,
because the acceptance is that the WIRING exists: a recorder nothing calls
would pass a unit test and record nothing in production.

Fails until the mint path calls the creator recorder (GREEN).
"""
from __future__ import annotations

import pytest

from atdd.state.agent_session import (
    KIND_AGENT_SESSION,
    REF_KIND_SESSION,
    REL_SESSION_CREATED_WORK_ITEM,
)

from ._publish_helpers import open_store, run_author_issue, stub_github_create

pytestmark = [pytest.mark.platform]

SLUG = "e009-creator-probe"
SESSION_ID = "6453e644-64cd-4254-add5-fa30135b52b1"


def _author_as_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION_ID)
    stub_github_create(monkeypatch)
    code, _ = run_author_issue([
        "--title", "Creator probe",
        "--slug", SLUG,
        "--type", "implementation",
        "--status", "INIT",
    ])
    return code


def test_e009_unit_001_mint_records_creating_session(tmp_path, monkeypatch):
    assert _author_as_agent(monkeypatch, tmp_path) == 0

    store, conn = open_store(tmp_path)
    try:
        session_refs = [r for r in store.external_refs.all() if r.ref_kind == REF_KIND_SESSION]
        assert len(session_refs) == 1, f"expected one session ref, got {session_refs}"
        ref = session_refs[0]
        assert ref.provider == "claude"
        assert ref.ref_value == SESSION_ID

        session = store.objects.get(ref.object_uid)
        assert session is not None
        assert session.kind == KIND_AGENT_SESSION

        rels = store.relationships.list(src_uid=ref.object_uid)
        creator = [r for r in rels if r.rel_type == REL_SESSION_CREATED_WORK_ITEM]
        assert len(creator) == 1, f"expected one creator edge, got {rels}"
        assert creator[0].dst_uid == SLUG
    finally:
        conn.close()


def test_e009_unit_001_no_role_is_written(tmp_path, monkeypatch):
    """Creation is a neutral fact — being a creator makes a session no role."""
    assert _author_as_agent(monkeypatch, tmp_path) == 0

    store, conn = open_store(tmp_path)
    try:
        blobs = [r.data or {} for r in store.external_refs.all()]
        blobs += [o.data or {} for o in [store.objects.get(SLUG)] if o is not None]
        for rel in store.relationships.list():
            blobs.append(rel.data or {})
    finally:
        conn.close()

    for blob in blobs:
        keys = {k.lower() for k in blob}
        assert "role" not in keys, f"a role was stored: {blob}"
        assert not keys & {"orchestrator", "worker"}, f"a role was stored: {blob}"
