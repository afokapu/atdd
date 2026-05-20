# URN: test:govern-lifecycle:rename-codex-conductor-md:E020-UNIT-004-conductor-md-tmpl-template-file-exists
# Acceptance: acc:govern-lifecycle:E020-UNIT-004-conductor-md-tmpl-template-file-exists
# WMBT: wmbt:govern-lifecycle:E020
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-004: The renamed persona template CONDUCTOR.md.tmpl exists in
templates/persona/codex/ and the old AGENTS.md.tmpl does NOT exist.

RED state: AGENTS.md.tmpl exists and CONDUCTOR.md.tmpl does not. This test
fails until the template file is renamed.
"""
from __future__ import annotations

from pathlib import Path

from atdd.coach.commands.sync import AgentConfigSync


def test_conductor_md_tmpl_exists_in_codex_persona_dir(tmp_path: Path) -> None:
    """CONDUCTOR.md.tmpl must exist in templates/persona/codex/."""
    sync = AgentConfigSync(target_dir=tmp_path)
    conductor_tmpl = sync.templates_dir / "persona" / "codex" / "CONDUCTOR.md.tmpl"

    assert conductor_tmpl.exists(), (
        f"CONDUCTOR.md.tmpl not found at {conductor_tmpl}; "
        "rename AGENTS.md.tmpl to CONDUCTOR.md.tmpl"
    )


def test_agents_md_tmpl_no_longer_exists_in_codex_persona_dir(tmp_path: Path) -> None:
    """AGENTS.md.tmpl must NOT exist in templates/persona/codex/ after rename."""
    sync = AgentConfigSync(target_dir=tmp_path)
    agents_tmpl = sync.templates_dir / "persona" / "codex" / "AGENTS.md.tmpl"

    assert not agents_tmpl.exists(), (
        f"AGENTS.md.tmpl still exists at {agents_tmpl}; "
        "remove it after renaming to CONDUCTOR.md.tmpl"
    )
