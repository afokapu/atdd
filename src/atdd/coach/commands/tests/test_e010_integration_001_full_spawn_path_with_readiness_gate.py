# URN: test:spawn-agents:worker-launch-prompt-readiness-gate:E010-INTEGRATION-001-full-spawn-path-with-readiness-gate
# Acceptance: acc:spawn-agents:E010-INTEGRATION-001-full-spawn-path-with-readiness-gate
# WMBT: wmbt:spawn-agents:E010
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E010-INTEGRATION-001 — the full cmd_spawn path exercises pre-trust →
surface creation → _wait_for_claude_ready → paste → _assert_worker_processing
in sequence, with a static-then-growing session jsonl (no capture_surface_text
needed — all backends are filesystem-capable).

RED: With the old implementation _assert_worker_processing skips silently
(hasattr guard returns early since the fake has no capture_surface_text).
After the fix it polls the jsonl size and the background-grown file satisfies
the assertion.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest


class _MinimalMux:
    """Fake that satisfies surface-creation primitives; no capture_surface_text.

    Proves the new _assert_worker_processing needs no multiplexer capture.
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


def test_full_spawn_path_with_readiness_gate(tmp_path, monkeypatch):
    """cmd_spawn runs the full pre-trust → ready-wait → paste → assert chain,
    with the session jsonl growing in a background thread to satisfy
    _assert_worker_processing."""
    from atdd.coach.commands.spawn import cmd_spawn

    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "5.0")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.02")

    worktree = tmp_path / "issue-795"
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
    jsonl = project_dir / "uuid-123.jsonl"
    jsonl.write_bytes(b"")  # empty file — exists so _wait_for_claude_ready passes

    # Background thread grows the jsonl continuously so _assert_worker_processing
    # detects growth regardless of when it samples initial_size.  cmd_spawn takes
    # ~0.7s before reaching _assert_worker_processing (apply_canonical_name_and_layout),
    # so we write every 0.1s for 3s to guarantee growth is seen.
    _stop_event = threading.Event()

    def _grow():
        while not _stop_event.wait(timeout=0.1):
            with jsonl.open("ab") as f:
                f.write(b"x")

    grow_thread = threading.Thread(target=_grow, daemon=True)
    grow_thread.start()

    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.write_text("You are the planner agent for issue #795.\n")

    fake_mux = _MinimalMux()

    try:
        cmd_spawn(
            persona="planner",
            llm="claude-code",
            worktree=worktree,
            issue=795,
            agent_id="planner-795-001",
            runtime_root=runtime,
            multiplexer=fake_mux,
        )
    finally:
        _stop_event.set()

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
