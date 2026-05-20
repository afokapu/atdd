# URN: test:govern-lifecycle:rename-codex-conductor-md:E020-UNIT-002-persona-template-maps-codex-to-conductor-md-tmpl
# Acceptance: acc:govern-lifecycle:E020-UNIT-002-persona-template-maps-codex-to-conductor-md-tmpl
# WMBT: wmbt:govern-lifecycle:E020
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-002: AgentConfigSync.PERSONA_TEMPLATE_FILES["codex"] resolves to
("codex", "CONDUCTOR.md.tmpl").

RED state: PERSONA_TEMPLATE_FILES["codex"] is currently ("codex", "AGENTS.md.tmpl").
This test fails until the constant is updated.
"""
from __future__ import annotations

from atdd.coach.commands.sync import AgentConfigSync


def test_persona_template_files_maps_codex_to_conductor_md_tmpl() -> None:
    """PERSONA_TEMPLATE_FILES["codex"] must be ("codex", "CONDUCTOR.md.tmpl")."""
    assert AgentConfigSync.PERSONA_TEMPLATE_FILES["codex"] == ("codex", "CONDUCTOR.md.tmpl")
