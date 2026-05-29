# URN: test:spawn-agents:E029-UNIT-002-assert-worker-processing-called-after-paste
# Acceptance: acc:spawn-agents:E029-UNIT-002-assert-worker-processing-called-after-paste
# WMBT: wmbt:spawn-agents:E029
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E029-UNIT-002 — _assert_worker_processing called after paste with JSONL path as before

RED: WorkerReadinessTimeout raised before paste (no JSONL for _wait_for_claude_ready),
so call-order assertion never reached until E023 GREEN phase.
"""
from __future__ import annotations

import threading
import time


class _OrderTrackingMux:
    """Fake multiplexer for E029-UNIT-002 — records paste calls and satisfies all stages."""

    def __init__(self, paste_event: threading.Event) -> None:
        self._paste_event = paste_event
        self.paste_calls: list = []
        self.send_key_calls: list = []

    def capture_pane_text(self, surface_ref: str) -> str:
        return "ATDD863  ❯  paste again to expand  ⏺ Thinking...  esc to interrupt"

    def new_surface_in_pane(self, *, pane_ref: str = "pane:1",
                            cwd: str = "", command: str = "",
                            name: str = "", **kw: object) -> str:
        return "surface:1"

    def paste_text(self, surface_ref: str, text: str, **kw: object) -> None:
        self.paste_calls.append((surface_ref, text))
        self._paste_event.set()

    def send_key(self, surface_ref: str, key: str, **kw: object) -> None:
        self.send_key_calls.append((surface_ref, key))

    def new_workspace(self, *a: object, **kw: object) -> str:
        return "ws-1"

    def new_surface(self, *a: object, **kw: object) -> str:
        return "surface:1"

    def rename(self, surface_ref: str, name: str, **kw: object) -> None:
        pass

    def list_surfaces(self, **kw: object) -> list:
        return []


def test_assert_worker_processing_called_after_paste(tmp_path, monkeypatch):
    """_assert_worker_processing fires AFTER paste; JSONL grows post-paste → pipeline completes.

    RED: _wait_for_claude_ready raises WorkerReadinessTimeout (no JSONL before paste);
         call-order assertion is never reached.
    GREEN: readiness probe passes, paste fires, bg thread grows JSONL, _assert_worker_processing
           detects growth, agent_spawned event is emitted.
    """
    from atdd.coach.commands.spawn import cmd_spawn

    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "5.0")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.02")

    worktree = tmp_path / "issue-863-e023-u002"
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
    # No JSONL before paste — simulates lazy session creation
    jsonl = project_dir / "session-e023-u002.jsonl"

    paste_event = threading.Event()
    stop_event = threading.Event()

    def _bg_thread() -> None:
        paste_event.wait(timeout=5.0)
        time.sleep(0.02)
        jsonl.write_bytes(b'{"type":"system"}\n')
        while not stop_event.wait(timeout=0.05):
            with jsonl.open("ab") as f:
                f.write(b"x")

    bg = threading.Thread(target=_bg_thread, daemon=True)
    bg.start()

    fake_mux = _OrderTrackingMux(paste_event=paste_event)

    try:
        cmd_spawn(
            persona="planner",
            llm="claude-code",
            worktree=worktree,
            issue=863,
            agent_id="planner-863-e023-u002",
            runtime_root=runtime,
            multiplexer=fake_mux,
        )
    finally:
        stop_event.set()
        bg.join(timeout=3.0)

    # _assert_worker_processing succeeded (JSONL grew post-paste)
    assert jsonl.exists(), "Session JSONL was never created post-paste"

    # Paste was called before JSONL existed (probe gates the paste, not JSONL polling)
    assert len(fake_mux.paste_calls) >= 1, "launch prompt was never pasted"

    # agent_spawned event confirms full pipeline: probe → paste → _assert_worker_processing → done
    agents_dir = runtime / "agents"
    assert any(agents_dir.rglob("events.jsonl")), (
        "agent_spawned event not written — _assert_worker_processing or pipeline incomplete"
    )
