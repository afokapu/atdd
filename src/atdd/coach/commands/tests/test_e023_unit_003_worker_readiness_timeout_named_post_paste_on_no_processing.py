# URN: test:spawn-agents:E023-UNIT-003-worker-readiness-timeout-named-post-paste-on-no-processing
# Acceptance: acc:spawn-agents:E023-UNIT-003-worker-readiness-timeout-named-post-paste-on-no-processing
# WMBT: wmbt:spawn-agents:E023
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""E023-UNIT-003 — WorkerReadinessTimeout on _assert_worker_processing timeout has post-paste language not boot language

RED: WorkerReadinessTimeout raised by _wait_for_claude_ready (boot-failure language: "No session .jsonl found")
     not by _assert_worker_processing (post-paste language: "did not begin processing"),
     because the pre-paste JSONL check fires first. GREEN: probe passes, paste fires, then
     static JSONL triggers _assert_worker_processing timeout with correct post-paste message.
"""
from __future__ import annotations

import pytest


class _BootReadyMux:
    """FakeMultiplexer that signals TUI ready but never shows 'paste again to expand'.

    Returns '❯' so SurfaceMarkerProbe passes, then holds on Thinking indicator
    so any retained _verify_stage('paste-landed') passes quickly too.
    """

    def capture_pane_text(self, surface_ref: str) -> str:
        return "❯  paste again to expand  ⏺ Thinking...  esc to interrupt"

    def paste_text(self, surface_ref: str, text: str, **kw: object) -> None:
        pass

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


def test_worker_readiness_timeout_named_post_paste_on_no_processing(tmp_path, monkeypatch):
    """probe passes + paste fires; static JSONL → _assert_worker_processing timeout with post-paste message.

    RED: _wait_for_claude_ready raises before paste with "No session .jsonl found" (boot language).
         Test fails because the raised exception has boot-failure language, not post-paste language.
    GREEN: readiness_probe.wait_for_ready sees '❯', paste is sent, then _assert_worker_processing
           times out with "did not begin processing" language. Test passes.
    """
    from atdd.coach.commands.spawn import WorkerReadinessTimeout, cmd_spawn

    # Short timeouts so test does not hang
    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "0.1")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.01")

    worktree = tmp_path / "issue-863-e023-u003"
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
    # Static JSONL: exists after the probe, never grows → _assert_worker_processing times out
    jsonl = project_dir / "session-static.jsonl"
    jsonl.write_bytes(b'{"type":"system","content":"initial"}\n')  # static — never appended

    fake_mux = _BootReadyMux()

    with pytest.raises(WorkerReadinessTimeout) as exc_info:
        cmd_spawn(
            persona="planner",
            llm="claude-code",
            worktree=worktree,
            issue=863,
            agent_id="planner-863-e023-u003",
            runtime_root=runtime,
            multiplexer=fake_mux,
        )

    msg = str(exc_info.value)

    # GREEN assertion: error came from _assert_worker_processing (post-paste gate),
    # NOT from the pre-paste JSONL boot wait.  The message must NOT say boot-failure language.
    assert "No session .jsonl found" not in msg, (
        "WorkerReadinessTimeout has boot-failure language ('No session .jsonl found') — "
        "this means the pre-paste gate still fires before paste (E023 not fixed). "
        f"Got: {msg!r}"
    )
    # The timeout must originate from post-paste processing failure
    assert "did not begin processing" in msg or "surface_ref" in msg.lower() or "surface:" in msg, (
        "WorkerReadinessTimeout message does not identify post-paste processing failure. "
        f"Got: {msg!r}"
    )
