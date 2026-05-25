# URN: test:spawn-agents:E018-UNIT-003-process-alive-stage-sequenced-after-surface-created
# Acceptance: acc:spawn-agents:E018-UNIT-003-process-alive-stage-sequenced-after-surface-created
# WMBT: wmbt:spawn-agents:E018
# Phase: GREEN
# Assertion: behavioral
"""E018-UNIT-003 — cmd_spawn calls _verify_process_alive after surface creation
and before agent_spawned is emitted; a ProcessNotAlive raised here prevents
agent_spawned.

RED: fails until _verify_process_alive is wired into cmd_spawn.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class _SurfaceCreatedMux:
    """Fake multiplexer that creates a surface normally."""

    name = "fake"

    def __init__(self):
        self.surface_calls = 0

    def new_workspace(self, *a, **kw):
        return "ws-1"

    def new_surface(self, *a, **kw):
        self.surface_calls += 1
        return "surface:857"

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
        return "⏺ Thinking..."


def test_process_alive_called_and_raises_prevents_agent_spawned(tmp_path, monkeypatch):
    """When _verify_process_alive raises ProcessNotAlive, agent_spawned is not emitted."""
    from atdd.coach.commands.spawn import ProcessNotAlive, cmd_spawn

    monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "cli-return")
    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "0.5")

    worktree = tmp_path / "issue-857"
    worktree.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.write_text("You are the planner for #857.\n")

    fake_mux = _SurfaceCreatedMux()

    # Patch _verify_process_alive to simulate a dead process
    def _dead_process_check(*args, **kwargs):
        raise ProcessNotAlive("process exited with code 1 (planner-857-dead)")

    with (
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=prompt_path),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD857"),
        patch("atdd.coach.commands.spawn._verify_process_alive", side_effect=_dead_process_check),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
    ):
        with pytest.raises(ProcessNotAlive):
            cmd_spawn(
                persona="planner",
                llm="claude-code",
                worktree=worktree,
                issue=857,
                agent_id="planner-857-dead",
                runtime_root=runtime,
                multiplexer=fake_mux,
            )

    # No agent_spawned event must exist
    agents_dir = runtime / "agents"
    spawned_events = list(agents_dir.rglob("events.jsonl")) if agents_dir.exists() else []
    assert not spawned_events, (
        f"agent_spawned must NOT be emitted when process-alive check fails. "
        f"Found events.jsonl at: {spawned_events}"
    )


def test_process_alive_called_before_agent_spawned_event(tmp_path, monkeypatch):
    """_verify_process_alive is invoked inside cmd_spawn — confirmed by tracking call order."""
    from atdd.coach.commands.spawn import cmd_spawn

    monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "cli-return")
    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "0.5")

    worktree = tmp_path / "issue-857b"
    worktree.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.write_text("launch prompt\n")

    call_log: list[str] = []

    def _record_alive(*args, **kwargs):
        call_log.append("verify_process_alive")

    def _record_spawned(*args, **kwargs):
        call_log.append("emit_agent_spawned")
        (runtime / "agents" / "planner-857b-ord").mkdir(parents=True, exist_ok=True)
        (runtime / "agents" / "planner-857b-ord" / "events.jsonl").write_text("")

    fake_mux = _SurfaceCreatedMux()

    with (
        patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=prompt_path),
        patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
        patch("atdd.coach.commands.spawn._pre_trust_worktree"),
        patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
        patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD857"),
        patch("atdd.coach.commands.spawn._verify_process_alive", side_effect=_record_alive),
        patch("atdd.coach.commands.spawn._emit_agent_spawned_event", side_effect=_record_spawned),
        patch("atdd.coach.commands.spawn._spawn_observer_if_configured"),
        patch("atdd.coach.commands.spawn._write_manifest"),
        patch("atdd.coach.commands.spawn.capture_session_uuid"),
        patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
    ):
        cmd_spawn(
            persona="planner",
            llm="claude-code",
            worktree=worktree,
            issue=857,
            agent_id="planner-857b-ord",
            runtime_root=runtime,
            multiplexer=fake_mux,
        )

    assert "verify_process_alive" in call_log, (
        "_verify_process_alive was never called inside cmd_spawn"
    )
    assert "emit_agent_spawned" in call_log, (
        "_emit_agent_spawned_event was never called (happy path)"
    )
    alive_idx = call_log.index("verify_process_alive")
    spawned_idx = call_log.index("emit_agent_spawned")
    assert alive_idx < spawned_idx, (
        f"_verify_process_alive must be called BEFORE agent_spawned. "
        f"Call order was: {call_log}"
    )
