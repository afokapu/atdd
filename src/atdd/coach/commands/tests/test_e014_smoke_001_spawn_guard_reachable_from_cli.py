# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E014-SMOKE-001-spawn-guard-reachable-from-cli
# Acceptance: acc:govern-lifecycle:E014-SMOKE-001-spawn-guard-reachable-from-cli
# WMBT: wmbt:govern-lifecycle:E014
# Phase: SMOKE
# Layer: backend.integration
# Assertion: behavioral

"""acc:govern-lifecycle:E014-SMOKE-001 — SpawnPermissionViolation is raised before multiplexer is invoked."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.integration
def test_spawn_guard_reachable_from_cli(tmp_path):
    from atdd.coach.commands.spawn import cmd_spawn, SpawnPermissionViolation, ADAPTER_REGISTRY

    def _unsafe_adapter(prompt_path):
        return "claude --dangerously-skip-permissions --some-flag"

    mock_mux = MagicMock()

    with patch.dict(ADAPTER_REGISTRY, {"test-unsafe": _unsafe_adapter}):
        with pytest.raises(SpawnPermissionViolation):
            cmd_spawn(
                persona="planner",
                llm="test-unsafe",
                worktree=tmp_path,
                issue=1,
                agent_id="a",
                runtime_root=tmp_path,
                multiplexer=mock_mux,
            )

    mock_mux.create_surface.assert_not_called(), "multiplexer must NOT be called when guard fires"
