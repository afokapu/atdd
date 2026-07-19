# URN: test:drive-state-machine:record-agent-session-identity:D003-UNIT-003-second-provider-is-yaml-only
# Acceptance: acc:drive-state-machine:D003-UNIT-003-second-provider-is-yaml-only
# WMBT: wmbt:drive-state-machine:D003
# Phase: RED
# Harness: unit
# Layer: integration
"""D003-UNIT-003 — a second provider costs one YAML row and zero code.

Issue #1540, success criterion 9. This is the load-bearing test for
core-agnosticity: the fixture table carries a provider (`other`) that appears
NOWHERE in atdd source, and it must resolve — and render its own resume
command — purely from the row. If core ever grows a branch per provider, this
goes red.
Fails until the table is read generically (GREEN).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from atdd.state import agent_session

from ._agent_session_helpers import write_provider_table

pytestmark = [pytest.mark.platform]


def test_d003_unit_003_second_provider_is_yaml_only(tmp_path, monkeypatch):
    table = write_provider_table(tmp_path)
    monkeypatch.setattr(agent_session, "PROVIDER_TABLE_PATH", table)
    agent_session.load_provider_table.cache_clear()

    resolved = agent_session.resolve_session({"TEST_OTHER_SESSION_ID": "abc-123"})

    assert resolved is not None
    assert resolved.provider == "other"
    assert resolved.session_id == "abc-123"
    # the projection renders that provider's command from its own row
    assert agent_session.resume_command(resolved, "/tmp/wt") == "other-cli attach abc-123 --dir /tmp/wt"


def test_d003_unit_003_no_provider_name_is_hardcoded_in_core():
    """The provider tags live in the table, not in the module."""
    source = Path(agent_session.__file__).read_text()
    # the shipped table names claude; the module itself must not
    assert "claude" not in source.lower()
    assert "CLAUDE_CODE_SESSION_ID" not in source
