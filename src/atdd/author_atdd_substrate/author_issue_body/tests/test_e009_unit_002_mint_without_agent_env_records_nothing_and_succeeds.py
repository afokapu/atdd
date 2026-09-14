# URN: test:drive-state-machine:record-agent-session-identity:E009-UNIT-002-mint-without-agent-env-records-nothing-and-succeeds
# Acceptance: acc:drive-state-machine:E009-UNIT-002-mint-without-agent-env-records-nothing-and-succeeds
# WMBT: wmbt:drive-state-machine:E009
# Phase: RED
# Harness: unit
# Layer: application
"""E009-UNIT-002 — a human minting from a plain shell records nothing, and succeeds.

Issue #1540. Capture is a no-op when no agent env var is present. The operator's
intent is the ISSUE, not the telemetry: an unrecorded creator is a missing nice-
to-have, while a failed mint is a broken command. So the absence of a session
must be an ordinary path, not an error path.
"""
from __future__ import annotations

import pytest

from atdd.state.agent_session import KIND_AGENT_SESSION, REF_KIND_SESSION

from ._publish_helpers import (
    open_store,
    run_author_issue,
    stub_github_create,
    work_item,
    work_item_uid,
)

pytestmark = [pytest.mark.platform]

SLUG = "e009-human-probe"


def test_e009_unit_002_mint_without_agent_env_records_nothing_and_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    # a plain shell: every known agent session var absent
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    stub_github_create(monkeypatch)

    code, _ = run_author_issue([
        "--title", "Human probe",
        "--slug", SLUG,
        "--type", "implementation",
        "--status", "INIT",
    ])

    assert code == 0, "a missing agent session must not fail the mint"

    store, conn = open_store(tmp_path)
    try:
        # the mint itself happened
        assert work_item(store, SLUG) is not None
        # but nothing was invented about who did it
        assert [r for r in store.external_refs.all() if r.ref_kind == REF_KIND_SESSION] == []
        assert store.objects.list(kind=KIND_AGENT_SESSION) == []
        assert store.relationships.list(dst_uid=work_item_uid(store, SLUG)) == []
    finally:
        conn.close()
