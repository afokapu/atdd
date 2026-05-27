# URN: test:spawn-agents:L003-SMOKE-001-session-jsonl-appears-after-launch-prompt-paste
# Acceptance: acc:spawn-agents:L003-SMOKE-001-session-jsonl-appears-after-launch-prompt-paste
# WMBT: wmbt:spawn-agents:L003
# Phase: SMOKE
# Layer: backend.smoke
# Runtime: python
# Assertion: behavioral
"""L003-SMOKE-001 — End-to-end SMOKE: session JSONL timestamp is newer than wall-clock time after launch-prompt paste

RED: fails until L003 is implemented — pending L003 GREEN phase.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="L003-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_session_jsonl_appears_after_launch_prompt_paste(tmp_path, monkeypatch):
    """End-to-end SMOKE: session JSONL mtime is strictly newer than wall-clock time after paste.

    Drives a real or simulated atdd coach spawn and asserts the session JSONL file
    appeared AFTER the launch-prompt paste (not before), confirming that the JSONL is
    a backend-round-trip artifact and not a TUI-boot artifact.

    Any regression that re-introduces JSONL-based boot detection will cause the JSONL
    to appear BEFORE paste → this test fails at SMOKE phase before it ships.
    """
    import time

    from atdd.coach.commands.spawn import cmd_spawn

    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "30.0")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.25")

    worktree = tmp_path / "issue-863-l003-smoke"
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

    # Remove any pre-existing JSONL so the test has a clean slate
    for f in project_dir.glob("*.jsonl"):
        f.unlink()

    paste_time: list[float] = []

    import atdd.coach.commands.spawn as spawn_mod
    _real_paste = None

    def _timing_paste(ref: str, text: str, **kw: object) -> None:
        paste_time.append(time.time())
        if _real_paste is not None:
            _real_paste(ref, text, **kw)

    # In SMOKE mode a real multiplexer is used; we wrap paste_text to record timing.
    # If no real multiplexer is available, skip gracefully.
    try:
        backend = spawn_mod._resolve_multiplexer()  # type: ignore[attr-defined]
    except Exception as exc:
        pytest.skip(f"L003-SMOKE-001: no real multiplexer available — {exc}")

    _real_paste = backend.paste_text
    backend.paste_text = _timing_paste  # type: ignore[method-assign]

    cmd_spawn(
        persona="planner",
        llm="claude-code",
        worktree=worktree,
        issue=863,
        agent_id="planner-863-l003-smoke",
        runtime_root=runtime,
        multiplexer=backend,
    )

    assert paste_time, "paste_text was never called — spawn did not inject launch prompt"

    # Find the session JSONL (should exist now — first backend round-trip triggered it)
    jsonl_files = list(project_dir.glob("*.jsonl"))
    assert jsonl_files, (
        f"No session JSONL found under {project_dir} — JSONL never created post-paste"
    )
    jsonl_path = jsonl_files[0]
    jsonl_mtime = os.path.getmtime(jsonl_path)

    assert jsonl_mtime > paste_time[0], (
        f"Session JSONL mtime ({jsonl_mtime:.3f}) is NOT newer than paste time ({paste_time[0]:.3f}) — "
        f"the JSONL appeared BEFORE paste, which means JSONL-based boot detection was re-introduced. "
        f"This is the L003 regression gate: JSONL must be a post-paste artifact."
    )
