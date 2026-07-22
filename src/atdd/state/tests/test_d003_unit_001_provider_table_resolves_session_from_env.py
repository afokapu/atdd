# URN: test:drive-state-machine:record-agent-session-identity:D003-UNIT-001-provider-table-resolves-session-from-env
# Acceptance: acc:drive-state-machine:D003-UNIT-001-provider-table-resolves-session-from-env
# WMBT: wmbt:drive-state-machine:D003
# Phase: RED
# Harness: unit
# Layer: integration
"""D003-UNIT-001 — the provider table resolves agent kind + session id from env.

Issue #1540. Identity is read from AMBIENT ENVIRONMENT, never asked of the
agent. The resolver walks the ``agent_session_env`` rows, takes the first whose
``session_env`` is present, and returns that row's provider tag plus the raw
value — carried through OPAQUE, since core never parses a provider's id.
Fails until ``resolve_session`` reads the table (GREEN).
"""
from __future__ import annotations

import pytest

from atdd.state import agent_session

from ._agent_session_helpers import write_provider_table

pytestmark = [pytest.mark.platform]


def test_d003_unit_001_provider_table_resolves_session_from_env(tmp_path, monkeypatch):
    table = write_provider_table(tmp_path)
    monkeypatch.setattr(agent_session, "PROVIDER_TABLE_PATH", table)
    agent_session.load_provider_table.cache_clear()

    resolved = agent_session.resolve_session(
        {"TEST_CLAUDE_SESSION_ID": "6453e644-64cd-4254-add5-fa30135b52b1"}
    )

    assert resolved is not None
    assert resolved.provider == "claude"
    # opaque: the id is whatever the provider set, unparsed
    assert resolved.session_id == "6453e644-64cd-4254-add5-fa30135b52b1"
