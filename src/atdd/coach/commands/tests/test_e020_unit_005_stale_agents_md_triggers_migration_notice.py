# URN: test:govern-lifecycle:rename-codex-conductor-md:E020-UNIT-005-stale-agents-md-triggers-migration-notice
# Acceptance: acc:govern-lifecycle:E020-UNIT-005-stale-agents-md-triggers-migration-notice
# WMBT: wmbt:govern-lifecycle:E020
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-005: When AGENTS.md with an ATDD managed block exists in the target
directory, sync() emits a migration notice directing the operator to delete
the stale file and use CONDUCTOR.md.

RED state: sync() currently does not detect or warn about stale AGENTS.md.
This test fails until migration notice logic is added to sync().
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from atdd.coach.commands.sync import AgentConfigSync

_MANAGED_AGENTS_MD = (
    "# --- ATDD:BEGIN (managed by atdd, do not edit) ---\n"
    "\nlegacy content\n\n"
    "# --- ATDD:END ---\n"
)


def test_stale_agents_md_emits_migration_notice(tmp_path: Path, capsys) -> None:
    """sync() must print a migration notice when AGENTS.md with managed block exists."""
    (tmp_path / "AGENTS.md").write_text(_MANAGED_AGENTS_MD)
    sync = AgentConfigSync(target_dir=tmp_path)

    rc = sync.sync(agents=["codex"])

    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert rc == 0
    assert "agents.md" in combined, "Migration notice must mention AGENTS.md"
    assert any(kw in combined for kw in ("deprecated", "conductor.md", "migrate")), (
        "Migration notice must mention the deprecation or CONDUCTOR.md"
    )


def test_stale_agents_md_still_creates_conductor_md(tmp_path: Path, capsys) -> None:
    """sync() must create CONDUCTOR.md even when stale AGENTS.md is present."""
    (tmp_path / "AGENTS.md").write_text(_MANAGED_AGENTS_MD)
    sync = AgentConfigSync(target_dir=tmp_path)

    sync.sync(agents=["codex"])

    assert (tmp_path / "CONDUCTOR.md").exists(), (
        "CONDUCTOR.md must be created regardless of stale AGENTS.md"
    )


def test_agents_md_without_managed_block_skips_notice(tmp_path: Path, capsys) -> None:
    """sync() must NOT emit migration notice when AGENTS.md has no managed block."""
    (tmp_path / "AGENTS.md").write_text("# My custom content\n\nNo ATDD block here.\n")
    sync = AgentConfigSync(target_dir=tmp_path)

    sync.sync(agents=["codex"])

    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "deprecated" not in combined, (
        "No migration notice for AGENTS.md without managed block"
    )
