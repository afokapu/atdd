# URN: test:spawn-agents:E018-INTEGRATION-001-immediately-failing-shim-triggers-escalation
# Acceptance: acc:spawn-agents:E018-INTEGRATION-001-immediately-failing-shim-triggers-escalation
# WMBT: wmbt:spawn-agents:E018
# Phase: GREEN
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E018-INTEGRATION-001 — when cmd_spawn runs in cli-return mode and the shim crashes
silently (simulated: output.log never receives a heartbeat byte), ProcessNotAlive is
raised by the real _verify_process_alive and no agent_spawned event is written.

The crash scenario is simulated by NOT creating output.log — the shim process tree is
not modelled here (a unit test concern); we test that the real liveness-check code in
cmd_spawn catches the missing heartbeat and blocks agent_spawned.

RED: fails until _verify_process_alive is wired into cmd_spawn.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class _SilentFakeMux:
    """Fake multiplexer: creates surfaces normally but never launches a real process.

    output.log is never written — simulates a shim that crashes before emitting
    any pty output (the exact failure mode from issue #857).
    """

    name = "fake"

    def resolve_focused_pane(self, workspace=None) -> str:
        return "pane:1"

    def new_surface(self, *a, **kw):
        return "surface:857-int"

    def new_surface_in_pane(self, pane_ref=None, cwd=None, command=None, name=None, **kw) -> str:
        return "surface:857-int"

    def new_workspace(self, *a, **kw):
        return "ws-1"

    def paste_text(self, *a, **kw):
        pass

    def send_key(self, *a, **kw):
        pass

    def send(self, *a, **kw):
        pass

    def rename(self, *a, **kw):
        pass

    def list_surfaces(self, **kw):
        return []

    def capture_pane_text(self, *a, **kw):
        return ""


def test_silent_shim_raises_process_not_alive_no_agent_spawned(tmp_path, monkeypatch):
    """In cli-return mode, if output.log never receives a heartbeat byte within the
    timeout, ProcessNotAlive is raised and agent_spawned is NOT emitted.

    Simulates a shim that crashes before writing any pty output.
    """
    from atdd.coach.commands.spawn import ProcessNotAlive, cmd_spawn

    monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "cli-return")
    # Very short timeout so the test completes quickly
    monkeypatch.setenv("ATDD_PROCESS_ALIVE_TIMEOUT", "0.2")

    worktree = tmp_path / "issue-857-int"
    worktree.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.write_text("launch prompt for integration test\n")

    fake_mux = _SilentFakeMux()

    with (
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=prompt_path),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD857"),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
        # _verify_process_alive NOT patched — real implementation runs
        # and raises ProcessNotAlive because output.log never appears
    ):
        with pytest.raises(ProcessNotAlive) as exc_info:
            cmd_spawn(
                persona="planner",
                llm="claude-code",
                worktree=worktree,
                issue=857,
                agent_id="planner-857-int-001",
                runtime_root=runtime,
                multiplexer=fake_mux,
            )

    assert "planner-857-int-001" in str(exc_info.value) or "output.log" in str(exc_info.value), (
        f"ProcessNotAlive message must identify the agent or log path. Got: {exc_info.value!r}"
    )

    # No agent_spawned event must exist
    agents_dir = runtime / "agents"
    spawned_events = list(agents_dir.rglob("events.jsonl")) if agents_dir.exists() else []
    assert not spawned_events, (
        f"agent_spawned must NOT be emitted when shim heartbeat never arrives. "
        f"Found: {spawned_events}"
    )


def test_process_not_alive_is_subclass_of_worker_readiness_timeout():
    """ProcessNotAlive inherits from WorkerReadinessTimeout so existing callers
    that catch WorkerReadinessTimeout continue to work without modification."""
    from atdd.coach.commands.spawn import ProcessNotAlive, WorkerReadinessTimeout

    assert issubclass(ProcessNotAlive, WorkerReadinessTimeout)
