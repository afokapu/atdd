# URN: test:spawn-agents:worker-launch-prompt-readiness-gate:E010-INTEGRATION-001-full-spawn-path-with-readiness-gate
# Acceptance: acc:spawn-agents:E010-INTEGRATION-001-full-spawn-path-with-readiness-gate
# WMBT: wmbt:spawn-agents:E010
# Phase: GREEN
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E010-INTEGRATION-001 — the full cmd_spawn path exercises pre-trust →
surface creation → _wait_for_claude_ready → paste → _assert_worker_processing
in sequence, with a FakeMultiplexer that simulates a worker coming up after
a short delay.

RED: _pre_trust_worktree, _wait_for_claude_ready, _assert_worker_processing,
and WorkerReadinessTimeout do not exist in spawn.py yet. The current code
goes straight from paste to capture_session_uuid without any readiness gate
(issue #795).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


class _ReadyAfterDelayMux:
    """Fake that simulates a worker coming up after a short delay.

    capture_surface_text returns:
      - calls 1-2: "Press up to edit queued messages" (not ready)
      - calls 3+:  "⏺ Thinking..." (worker is processing)
    """

    def __init__(self):
        self._call_count = 0
        self.paste_calls: list = []
        self.send_key_calls: list = []

    def new_workspace(self, *a, **kw):
        return "ws-1"

    def new_surface(self, *a, **kw):
        return "surface:1"

    def paste_text(self, surface_ref, text, **kw):
        self.paste_calls.append((surface_ref, text))

    def send_key(self, surface_ref, key, **kw):
        self.send_key_calls.append((surface_ref, key))

    def rename(self, surface_ref, name, **kw):
        pass

    def list_surfaces(self, **kw):
        return []

    def capture_surface_text(self, surface_ref: str) -> str:
        self._call_count += 1
        if self._call_count <= 2:
            return "Press up to edit queued messages"
        return "⏺ Thinking..."


def test_full_spawn_path_with_readiness_gate(tmp_path, monkeypatch):
    """cmd_spawn runs the full pre-trust → ready-wait → paste → assert chain."""
    from atdd.coach.commands.spawn import cmd_spawn

    # Use short but safe timeouts: 5s ready-wait, 20ms poll.
    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "5.0")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.02")

    worktree = tmp_path / "issue-795"
    worktree.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    # Stub claude.json path so real ~/.claude.json is never touched.
    claude_json = tmp_path / ".claude.json"
    monkeypatch.setenv("ATDD_CLAUDE_JSON_PATH", str(claude_json))

    # Stub claude projects dir so real ~/.claude/projects/ is never touched.
    claude_projects = tmp_path / ".claude" / "projects"
    claude_projects.mkdir(parents=True)
    monkeypatch.setenv("ATDD_CLAUDE_PROJECTS_DIR", str(claude_projects))

    # Pre-create the session file using the same key formula as _claude_project_key
    # so the readiness poll finds it immediately. Since _wait_for_claude_ready
    # now accepts any .jsonl regardless of mtime, we don't need background threads.
    from atdd.coach.utils.session_naming_apply import _claude_project_key

    project_key = _claude_project_key(worktree)
    project_dir = claude_projects / project_key
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "uuid-123.jsonl").write_text("{}")

    # Write a minimal launch prompt.
    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.write_text("You are the planner agent for issue #795.\n")

    fake_mux = _ReadyAfterDelayMux()

    cmd_spawn(
        persona="planner",
        llm="claude-code",
        worktree=worktree,
        issue=795,
        agent_id="planner-795-001",
        runtime_root=runtime,
        multiplexer=fake_mux,
    )

    # 1. pre-trust wrote to claude.json.
    data = json.loads(claude_json.read_text())
    assert data["projects"][str(worktree)]["hasTrustDialogAccepted"] is True

    # 2. paste and Enter were sent (prompt was injected).
    assert len(fake_mux.paste_calls) >= 1
    assert len(fake_mux.send_key_calls) >= 1

    # 3. The agent_spawned event exists under runtime.
    agents_dir = runtime / "agents"
    assert any(agents_dir.rglob("events.jsonl")), (
        "agent_spawned event was not written to runtime/agents/"
    )
