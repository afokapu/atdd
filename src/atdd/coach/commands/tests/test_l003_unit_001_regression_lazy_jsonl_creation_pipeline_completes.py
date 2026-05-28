# URN: test:spawn-agents:L003-UNIT-001-regression-lazy-jsonl-creation-pipeline-completes
# Acceptance: acc:spawn-agents:L003-UNIT-001-regression-lazy-jsonl-creation-pipeline-completes
# WMBT: wmbt:spawn-agents:L003
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""L003-UNIT-001 — Regression: lazy JSONL creation (probe passes on surface marker, JSONL absent before paste, written after paste) — pipeline completes

RED: WorkerReadinessTimeout raised by _wait_for_claude_ready (no JSONL before paste).
     This confirms the deadlock scenario. GREEN: SurfaceMarkerProbe gates on '❯' (no JSONL needed);
     background thread creates + grows JSONL post-paste; pipeline completes without timeout.
"""
from __future__ import annotations

import threading
import time


class _LazySessionMux:
    """Fake multiplexer for L003-UNIT-001 — records paste time, satisfies all stage checks."""

    def __init__(self, paste_event: threading.Event) -> None:
        self._paste_event = paste_event
        self.paste_calls: list = []
        self.paste_time: float = 0.0

    def capture_pane_text(self, surface_ref: str) -> str:
        return "ATDD863  ❯  paste again to expand  ⏺ Thinking...  esc to interrupt"

    def new_surface_in_pane(self, *, pane_ref: str = "pane:1",
                            cwd: str = "", command: str = "",
                            name: str = "", **kw: object) -> str:
        return "surface:1"

    def paste_text(self, surface_ref: str, text: str, **kw: object) -> None:
        self.paste_calls.append((surface_ref, text))
        self.paste_time = time.monotonic()
        self._paste_event.set()

    def send_key(self, surface_ref: str, key: str, **kw: object) -> None:
        pass

    def new_workspace(self, *a: object, **kw: object) -> str:
        return "ws-1"

    def new_surface(self, *a: object, **kw: object) -> str:
        return "surface:1"

    def rename(self, surface_ref: str, name: str, **kw: object) -> None:
        pass

    def list_surfaces(self, **kw: object) -> list:
        return []


def test_regression_lazy_jsonl_creation_pipeline_completes(tmp_path, monkeypatch):
    """Regression gate: lazy JSONL creation must not deadlock the spawn pipeline.

    Scenario: FakeMultiplexer returns '❯' (TUI ready), but NO JSONL exists at probe time.
    A background thread writes the JSONL exactly 0.1s after paste fires — simulating
    'first backend round-trip' semantics (claude-code 2.1.150 lazy session creation).

    RED: _wait_for_claude_ready polls for JSONL before paste → raises WorkerReadinessTimeout.
    GREEN: SurfaceMarkerProbe sees '❯', paste fires, bg thread creates+grows JSONL,
           _assert_worker_processing detects growth, pipeline completes.
    """
    from atdd.coach.commands.spawn import cmd_spawn

    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "5.0")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.02")

    worktree = tmp_path / "issue-863-l003-u001"
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

    # KEY: no JSONL exists before paste — simulates lazy session creation
    jsonl = project_dir / "session-lazy-l003.jsonl"
    assert not jsonl.exists(), "Test setup error: JSONL must not exist before spawn"

    paste_event = threading.Event()
    stop_event = threading.Event()

    def _bg_thread() -> None:
        """Simulate lazy JSONL creation: write JSONL 0.1s after paste fires."""
        paste_event.wait(timeout=5.0)
        time.sleep(0.1)  # Simulate latency of first backend round-trip
        jsonl.write_bytes(b'{"type":"system","content":"lazy-init"}\n')
        while not stop_event.wait(timeout=0.05):
            with jsonl.open("ab") as f:
                f.write(b"x")

    bg = threading.Thread(target=_bg_thread, daemon=True)
    bg.start()

    fake_mux = _LazySessionMux(paste_event=paste_event)

    try:
        cmd_spawn(
            persona="planner",
            llm="claude-code",
            worktree=worktree,
            issue=863,
            agent_id="planner-863-l003-u001",
            runtime_root=runtime,
            multiplexer=fake_mux,
        )
    finally:
        stop_event.set()
        bg.join(timeout=5.0)

    # ── Regression assertions ──────────────────────────────────────────────────

    # 1. Paste was called (launch prompt was delivered to TUI)
    assert len(fake_mux.paste_calls) >= 1, "Regression: paste was never called"

    # 2. JSONL was created POST-paste (confirming lazy-creation semantics)
    assert jsonl.exists(), "Regression: JSONL file never created by background thread"

    # 3. Pipeline completed (agent_spawned event emitted)
    agents_dir = runtime / "agents"
    assert any(agents_dir.rglob("events.jsonl")), (
        "Regression: agent_spawned event not written — pipeline did not complete"
    )
