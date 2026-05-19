# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E014-UNIT-002-clean-command-passes-guard
# Acceptance: acc:govern-lifecycle:E014-UNIT-002-clean-command-passes-guard
# WMBT: wmbt:govern-lifecycle:E014
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E014-UNIT-002 — cmd_spawn does NOT raise SpawnPermissionViolation for safe command."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def test_clean_command_passes_guard(tmp_path):
    from atdd.coach.commands.spawn import cmd_spawn, SpawnPermissionViolation

    mock_mux = MagicMock()
    mock_mux.create_surface.return_value = "ATDD1"
    mock_mux.send_text = MagicMock()
    mock_mux.send_key = MagicMock()

    try:
        cmd_spawn(
            persona="planner",
            llm="claude-code",
            worktree=tmp_path,
            issue=1,
            agent_id="test-agent",
            runtime_root=tmp_path,
            multiplexer=mock_mux,
        )
    except SpawnPermissionViolation:
        raise AssertionError("SpawnPermissionViolation must NOT be raised for a safe claude-code command")
    except Exception:
        pass
