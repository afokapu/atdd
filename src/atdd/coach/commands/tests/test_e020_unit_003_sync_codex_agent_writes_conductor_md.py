# URN: test:govern-lifecycle:rename-codex-conductor-md:E020-UNIT-003-sync-codex-agent-writes-conductor-md
# Acceptance: acc:govern-lifecycle:E020-UNIT-003-sync-codex-agent-writes-conductor-md
# WMBT: wmbt:govern-lifecycle:E020
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-003: AgentConfigSync.sync(agents=["codex"]) creates CONDUCTOR.md,
not AGENTS.md, in the target directory.

RED state: sync() currently creates AGENTS.md for the codex agent. This test
fails until AGENT_FILES["codex"] is updated to "CONDUCTOR.md".
"""
from __future__ import annotations

from pathlib import Path

from atdd.coach.commands.sync import AgentConfigSync


def test_sync_codex_creates_conductor_md_not_agents_md(tmp_path: Path) -> None:
    """sync(["codex"]) must create CONDUCTOR.md and must NOT create AGENTS.md."""
    sync = AgentConfigSync(target_dir=tmp_path)

    rc = sync.sync(agents=["codex"])

    assert rc == 0
    assert (tmp_path / "CONDUCTOR.md").exists(), "CONDUCTOR.md was not created"
    assert not (tmp_path / "AGENTS.md").exists(), "AGENTS.md must not be created for codex"


def test_sync_codex_conductor_md_contains_atdd_block(tmp_path: Path) -> None:
    """CONDUCTOR.md created by sync must contain the ATDD managed block."""
    sync = AgentConfigSync(target_dir=tmp_path)
    sync.sync(agents=["codex"])

    content = (tmp_path / "CONDUCTOR.md").read_text()
    assert "# --- ATDD:BEGIN" in content
    assert "# --- ATDD:END" in content
