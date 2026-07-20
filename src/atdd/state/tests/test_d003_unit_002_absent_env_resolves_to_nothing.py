# URN: test:drive-state-machine:record-agent-session-identity:D003-UNIT-002-absent-env-resolves-to-nothing
# Acceptance: acc:drive-state-machine:D003-UNIT-002-absent-env-resolves-to-nothing
# WMBT: wmbt:drive-state-machine:D003
# Phase: RED
# Harness: unit
# Layer: integration
"""D003-UNIT-002 — no agent env var means no session, not an error.

Issue #1540. A human at a plain shell is not an agent. The resolver must yield
nothing rather than raising or inventing an identity, because this same path
runs inside `atdd author issue` and the post-commit hook, where neither may
fail on a human's behalf.
Fails until ``resolve_session`` returns None on a bare environment (GREEN).
"""
from __future__ import annotations

import pytest

from atdd.state import agent_session

from ._agent_session_helpers import write_provider_table

pytestmark = [pytest.mark.platform]


def test_d003_unit_002_absent_env_resolves_to_nothing(tmp_path, monkeypatch):
    table = write_provider_table(tmp_path)
    monkeypatch.setattr(agent_session, "PROVIDER_TABLE_PATH", table)
    agent_session.load_provider_table.cache_clear()

    # an environment with unrelated variables only — no mapped session_env
    assert agent_session.resolve_session({"HOME": "/tmp", "PATH": "/usr/bin"}) is None
    assert agent_session.resolve_session({}) is None
