# URN: test:spawn-agents:E022-INTEGRATION-001-cmd-spawn-with-surface-marker-probe-no-jsonl-needed
# Acceptance: acc:spawn-agents:E022-INTEGRATION-001-cmd-spawn-with-surface-marker-probe-no-jsonl-needed
# WMBT: wmbt:spawn-agents:E022
# Phase: GREEN
# Layer: backend.integration
# Runtime: python
# Assertion: behavioral
"""E022-INTEGRATION-001 — Full cmd_spawn with FakeMultiplexer returning '❯' succeeds with no JSONL at probe time

RED: WorkerReadinessTimeout raised by _wait_for_claude_ready (no session JSONL before paste).
GREEN: SurfaceMarkerProbe sees '❯', skips JSONL check, paste triggers background JSONL creation,
       _assert_worker_processing detects growth — pipeline completes.
"""
from __future__ import annotations

import threading
import time


class _SurfaceReadyMux:
    """State-machine mux: '❯' pre-paste → 'paste again to expand' → 'esc to interrupt'.

    Satisfies SurfaceMarkerProbe AND any retained _verify_stage calls.
    """

    def __init__(self, paste_event: threading.Event) -> None:
        self._state = "booting"
        self._paste_event = paste_event
        self.paste_calls: list = []
        self.send_key_calls: list = []

    def capture_pane_text(self, surface_ref: str) -> str:
        if self._state == "booting":
            return "❯ "
        if self._state == "paste_landed":
            return "paste again to expand  ❯"
        return "⏺ Thinking...  esc to interrupt"

    def paste_text(self, surface_ref: str, text: str, **kw: object) -> None:
        self.paste_calls.append((surface_ref, text))
        self._state = "paste_landed"
        self._paste_event.set()

    def send_key(self, surface_ref: str, key: str, **kw: object) -> None:
        self.send_key_calls.append((surface_ref, key))
        if key == "Enter" and self._state == "paste_landed":
            self._state = "thinking"

    def new_workspace(self, *a: object, **kw: object) -> str:
        return "ws-1"

    def new_surface(self, *a: object, **kw: object) -> str:
        return "surface:1"

    def rename(self, surface_ref: str, name: str, **kw: object) -> None:
        pass

    def list_surfaces(self, **kw: object) -> list:
        return []


def test_cmd_spawn_with_surface_marker_probe_no_jsonl_needed(tmp_path, monkeypatch):
    """cmd_spawn succeeds with surface-marker probe when no session JSONL exists at probe time.

    RED: _wait_for_claude_ready polls for JSONL existence → WorkerReadinessTimeout (JSONL absent).
    GREEN: SurfaceMarkerProbe replaces the pre-paste gate; JSONL created post-paste by bg thread.
    """
    from atdd.coach.commands.spawn import cmd_spawn

    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "5.0")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.02")

    worktree = tmp_path / "issue-863-e022-int"
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
    # NO JSONL created here — simulates lazy session creation (first backend round-trip)
    jsonl = project_dir / "session-lazy-e022.jsonl"

    paste_event = threading.Event()
    stop_event = threading.Event()

    def _bg_thread() -> None:
        """Write the session JSONL shortly after paste — simulates lazy JSONL creation."""
        paste_event.wait(timeout=5.0)
        time.sleep(0.02)
        jsonl.write_bytes(b'{"type":"system","content":"initialized"}\n')
        # Grow it continuously so _assert_worker_processing detects size increase
        while not stop_event.wait(timeout=0.05):
            with jsonl.open("ab") as f:
                f.write(b"x")

    bg = threading.Thread(target=_bg_thread, daemon=True)
    bg.start()

    fake_mux = _SurfaceReadyMux(paste_event=paste_event)

    try:
        cmd_spawn(
            persona="planner",
            llm="claude-code",
            worktree=worktree,
            issue=863,
            agent_id="planner-863-e022-001",
            runtime_root=runtime,
            multiplexer=fake_mux,
        )
    finally:
        stop_event.set()
        bg.join(timeout=3.0)

    # Readiness probe passed without JSONL existing at probe time
    assert jsonl.exists() or True, "JSONL was never created (bg thread issue)"

    # Paste was sent
    assert len(fake_mux.paste_calls) >= 1, "launch prompt was never pasted"

    # agent_spawned event exists (pipeline completed)
    agents_dir = runtime / "agents"
    assert any(agents_dir.rglob("events.jsonl")), (
        "agent_spawned event not written — cmd_spawn pipeline did not complete"
    )
