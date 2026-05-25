# URN: test:spawn-agents:E018-INTEGRATION-001-immediately-failing-shim-triggers-escalation
# Acceptance: acc:spawn-agents:E018-INTEGRATION-001-immediately-failing-shim-triggers-escalation
# WMBT: wmbt:spawn-agents:E018
# Phase: GREEN
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E018-INTEGRATION-001 — when cmd_spawn is driven with a shim command pointing to an
immediately-failing binary (exit 1), the process-alive stage raises ProcessNotAlive
and no agent_spawned event is written.

RED: fails until _verify_process_alive is wired into cmd_spawn and actually launches the process.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class _ProcessLaunchingMux:
    """Fake multiplexer that actually launches the command as a subprocess.

    Captures the spawned process object so _verify_process_alive can poll it.
    """

    name = "fake"

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self.surface_ref = "surface:857-integration"

    def new_surface(self, *, command=None, cwd=None, **kw):
        if command:
            self._proc = subprocess.Popen(
                command,
                shell=True,
                cwd=str(cwd) if cwd else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
            )
        return self.surface_ref

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
        return "Press Enter to send"

    def terminate(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()


def test_failing_shim_raises_process_not_alive_no_agent_spawned(tmp_path, monkeypatch):
    """With a shim command that exits 1 immediately, ProcessNotAlive is raised
    and no agent_spawned event exists in runtime/agents/."""
    from atdd.coach.commands.spawn import ProcessNotAlive, cmd_spawn

    monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "cli-return")
    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "2.0")

    worktree = tmp_path / "issue-857-int"
    worktree.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.write_text("launch prompt for integration test\n")

    failing_script = tmp_path / "fail_immediately.py"
    failing_script.write_text("import sys; sys.exit(1)\n")
    failing_cmd = f"{sys.executable} {failing_script}"

    fake_mux = _ProcessLaunchingMux()

    try:
        with (
            patch("atdd.coach.commands.spawn._render_launch_prompt", return_value=prompt_path),
            patch("atdd.coach.commands.spawn.apply_canonical_name_and_layout"),
            patch("atdd.coach.commands.spawn._pre_trust_worktree"),
            patch("atdd.coach.commands.spawn.compute_repo_short_name", return_value="test"),
            patch("atdd.coach.commands.spawn.compute_issue_surface_name", return_value="ATDD857"),
            patch("atdd.coach.utils.config.load_atdd_config", return_value=MagicMock()),
        ):
            from atdd.coach.commands.spawn import AdapterConfig

            # Override the adapter so the "adapter" is our immediately-failing script
            import atdd.coach.commands.spawn as spawn_mod
            original = dict(spawn_mod.ADAPTER_REGISTRY)
            spawn_mod.ADAPTER_REGISTRY["claude-code"] = AdapterConfig(
                build_command=lambda prompt_path: failing_cmd,
                permission_flags=[],
                allowed_tools=[],
            )
            try:
                with pytest.raises((ProcessNotAlive, Exception)) as exc_info:
                    cmd_spawn(
                        persona="planner",
                        llm="claude-code",
                        worktree=worktree,
                        issue=857,
                        agent_id="planner-857-int-001",
                        runtime_root=runtime,
                        multiplexer=fake_mux,
                    )
                # The exception must be related to the process dying, not a generic error
                assert exc_info.type is ProcessNotAlive or issubclass(
                    exc_info.type, ProcessNotAlive
                ), (
                    f"Expected ProcessNotAlive, got {exc_info.type.__name__}: {exc_info.value}"
                )
            finally:
                spawn_mod.ADAPTER_REGISTRY["claude-code"] = original["claude-code"]
    finally:
        fake_mux.terminate()

    # No agent_spawned event must exist
    agents_dir = runtime / "agents"
    spawned_events = list(agents_dir.rglob("events.jsonl")) if agents_dir.exists() else []
    assert not spawned_events, (
        f"agent_spawned must NOT be emitted when the shim exits immediately. "
        f"Found: {spawned_events}"
    )
