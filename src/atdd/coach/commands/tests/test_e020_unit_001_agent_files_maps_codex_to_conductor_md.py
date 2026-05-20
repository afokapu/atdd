# URN: test:govern-lifecycle:rename-codex-conductor-md:E020-UNIT-001-agent-files-maps-codex-to-conductor-md
# Acceptance: acc:govern-lifecycle:E020-UNIT-001-agent-files-maps-codex-to-conductor-md
# WMBT: wmbt:govern-lifecycle:E020
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-001: AgentConfigSync.AGENT_FILES["codex"] resolves to "CONDUCTOR.md".

RED state: AGENT_FILES["codex"] is currently "AGENTS.md". This test fails
until the constant is updated to "CONDUCTOR.md".
"""
from __future__ import annotations

from atdd.coach.commands.sync import AgentConfigSync


def test_agent_files_maps_codex_to_conductor_md() -> None:
    """AGENT_FILES["codex"] must be "CONDUCTOR.md", not "AGENTS.md"."""
    assert AgentConfigSync.AGENT_FILES["codex"] == "CONDUCTOR.md"
