# URN: test:spawn-agents:coach-spawn-step-by-step-verify-each-stage:E011-INTEGRATION-001-full-spawn-path-verify-each-stage
# Acceptance: acc:spawn-agents:E011-INTEGRATION-001-full-spawn-path-verify-each-stage
# WMBT: wmbt:spawn-agents:E011
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E011-INTEGRATION-001 — the full cmd_spawn path exercises all four verify stages
in sequence (claude-up, rename-accepted, paste-landed, prompt-submitted) with a
FakeMultiplexer that scripts correct progression through each stage.

RED: _verify_stage, capture_pane_text on FakeMultiplexer, and RenameNotAccepted/
PasteDidNotLand/PromptNotSubmitted exceptions do not exist yet (issue #799).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


class _StageProgressMux:
    """Fake multiplexer that scripts capture_pane_text responses per stage.

    The progression simulates a worker that:
    1. Boots Claude (shows Anthropic/accept-edits markers).
    2. Accepts /rename (canonical name appears in pane).
    3. Receives paste (collapse indicator appears).
    4. Starts processing (thinking marker appears).
    """

    def __init__(self):
        self._call_count = 0
        self.paste_calls: list = []
        self.send_key_calls: list = []
        self.send_calls: list = []

    def new_workspace(self, *a, **kw):
        return "ws-1"

    def new_surface(self, *a, **kw):
        return "surface:1"

    def paste_text(self, surface_ref, text, **kw):
        self.paste_calls.append((surface_ref, text))

    def send_key(self, surface_ref, key, **kw):
        self.send_key_calls.append((surface_ref, key))

    def send(self, surface_ref, text, **kw):
        self.send_calls.append((surface_ref, text))

    def rename(self, surface_ref, name, **kw):
        pass

    def list_surfaces(self, **kw):
        return []

    def capture_pane_text(self, surface_ref: str) -> str:
        """Return staged captures simulating correct progression."""
        self._call_count += 1
        # Calls 1-2: claude-up check — TUI ready
        if self._call_count <= 2:
            return "Anthropic · ⏵⏵ accept edits"
        # Calls 3-4: rename-accepted check
        if self._call_count <= 4:
            return "ATDD799 · Anthropic"
        # Calls 5-6: paste-landed check
        if self._call_count <= 6:
            return "paste again to expand · 1 line"
        # Calls 7+: prompt-submitted check — thinking started
        return "⏺ Thinking..."

    def capture_surface_text(self, surface_ref: str) -> str:
        """Also expose capture_surface_text for _assert_worker_processing compat."""
        return self.capture_pane_text(surface_ref)


def test_full_spawn_path_verify_each_stage(tmp_path, monkeypatch):
    """cmd_spawn runs through all four verify stages without raising."""
    from atdd.coach.commands.spawn import cmd_spawn

    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "5.0")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.02")

    worktree = tmp_path / "issue-799"
    worktree.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    claude_json = tmp_path / ".claude.json"
    monkeypatch.setenv("ATDD_CLAUDE_JSON_PATH", str(claude_json))

    claude_projects = tmp_path / ".claude" / "projects"
    claude_projects.mkdir(parents=True)
    monkeypatch.setenv("ATDD_CLAUDE_PROJECTS_DIR", str(claude_projects))

    from atdd.coach.utils.session_naming_apply import _claude_project_key

    project_key = _claude_project_key(worktree)
    project_dir = claude_projects / project_key
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "uuid-799.jsonl").write_text("{}")

    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.write_text("You are the planner agent for issue #799.\n")

    fake_mux = _StageProgressMux()

    cmd_spawn(
        persona="planner",
        llm="claude-code",
        worktree=worktree,
        issue=799,
        agent_id="planner-799-001",
        runtime_root=runtime,
        multiplexer=fake_mux,
    )

    # paste and Enter were sent.
    assert len(fake_mux.paste_calls) >= 1
    assert len(fake_mux.send_key_calls) >= 1

    # agent_spawned event was written.
    agents_dir = runtime / "agents"
    assert any(agents_dir.rglob("events.jsonl")), (
        "agent_spawned event was not written to runtime/agents/"
    )


def test_full_spawn_path_no_agent_spawned_when_paste_fails(tmp_path, monkeypatch):
    """cmd_spawn does NOT emit agent_spawned when paste stage fails verification."""
    from atdd.coach.commands.spawn import PasteDidNotLand, cmd_spawn

    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "5.0")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.02")

    worktree = tmp_path / "issue-799b"
    worktree.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    claude_json = tmp_path / ".claude.json"
    monkeypatch.setenv("ATDD_CLAUDE_JSON_PATH", str(claude_json))

    claude_projects = tmp_path / ".claude" / "projects"
    claude_projects.mkdir(parents=True)
    monkeypatch.setenv("ATDD_CLAUDE_PROJECTS_DIR", str(claude_projects))

    from atdd.coach.utils.session_naming_apply import _claude_project_key

    project_key = _claude_project_key(worktree)
    project_dir = claude_projects / project_key
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "uuid-799b.jsonl").write_text("{}")

    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.write_text("You are the planner agent for issue #799.\n")

    class _PasteFailsMux:
        """Mux where paste-landed never signals — simulates lost paste."""

        def __init__(self):
            self.paste_calls: list = []
            self.send_key_calls: list = []
            self._call_count = 0

        def new_workspace(self, *a, **kw):
            return "ws-1"

        def new_surface(self, *a, **kw):
            return "surface:1"

        def paste_text(self, surface_ref, text, **kw):
            self.paste_calls.append((surface_ref, text))

        def send_key(self, surface_ref, key, **kw):
            self.send_key_calls.append((surface_ref, key))

        def send(self, surface_ref, text, **kw):
            pass

        def rename(self, surface_ref, name, **kw):
            pass

        def list_surfaces(self, **kw):
            return []

        def capture_pane_text(self, surface_ref: str) -> str:
            self._call_count += 1
            # Always idle — paste never shows
            return "Press Enter to send"

        def capture_surface_text(self, surface_ref: str) -> str:
            return self.capture_pane_text(surface_ref)

    fake_mux = _PasteFailsMux()

    with pytest.raises(Exception):
        cmd_spawn(
            persona="planner",
            llm="claude-code",
            worktree=worktree,
            issue=799,
            agent_id="planner-799-002",
            runtime_root=runtime,
            multiplexer=fake_mux,
        )

    # No agent_spawned event should exist.
    agents_dir = runtime / "agents"
    assert not any(agents_dir.rglob("events.jsonl")), (
        "agent_spawned should NOT be emitted when paste-landed verification fails"
    )
