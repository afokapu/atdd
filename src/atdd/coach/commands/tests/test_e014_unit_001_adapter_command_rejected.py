# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E014-UNIT-001-adapter-command-rejected
# Acceptance: acc:govern-lifecycle:E014-UNIT-001-adapter-command-rejected
# WMBT: wmbt:govern-lifecycle:E014
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E014-UNIT-001 — cmd_spawn raises SpawnPermissionViolation when adapter emits forbidden flag."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_adapter_command_rejected(tmp_path):
    from atdd.coach.commands.spawn import cmd_spawn, SpawnPermissionViolation, ADAPTER_REGISTRY

    def _unsafe_adapter(prompt_path):
        return "claude --dangerously-skip-permissions"

    with patch.dict(ADAPTER_REGISTRY, {"unsafe-claude": _unsafe_adapter}):
        with pytest.raises(SpawnPermissionViolation) as exc_info:
            cmd_spawn(
                persona="planner",
                llm="unsafe-claude",
                worktree=tmp_path,
                issue=1,
                agent_id="test-agent",
                runtime_root=tmp_path,
            )

    assert "--dangerously-skip-permissions" in str(exc_info.value)
