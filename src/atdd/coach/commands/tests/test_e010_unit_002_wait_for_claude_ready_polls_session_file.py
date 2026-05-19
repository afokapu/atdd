# URN: test:spawn-agents:worker-launch-prompt-readiness-gate:E010-UNIT-002-wait-for-claude-ready-polls-session-file
# Acceptance: acc:spawn-agents:E010-UNIT-002-wait-for-claude-ready-polls-session-file
# WMBT: wmbt:spawn-agents:E010
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E010-UNIT-002 — _wait_for_claude_ready returns once a .jsonl session
file appears in the project directory, within the bounded timeout.

RED: _wait_for_claude_ready and WorkerReadinessTimeout do not exist in
spawn.py yet. The current code puts a 1.5s sleep inside capture_session_uuid
*after* the paste — too late to gate the paste itself (issue #795).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest


class _FakeMux:
    """Minimal fake with capture_surface_text returning a TUI-ready marker."""

    def capture_surface_text(self, surface_ref: str) -> str:
        return "⏵⏵ accept edits"


def test_wait_returns_when_session_file_appears(tmp_path):
    from atdd.coach.commands.spawn import _wait_for_claude_ready

    project_dir = tmp_path / ".claude" / "projects" / "project-key"
    project_dir.mkdir(parents=True)

    spawn_time = time.time()
    fake_mux = _FakeMux()

    # Background thread creates the session file after a short delay.
    def _create_file():
        time.sleep(0.05)
        session_file = project_dir / "abc123.jsonl"
        session_file.write_text("{}")

    t = threading.Thread(target=_create_file, daemon=True)
    t.start()

    start = time.monotonic()
    _wait_for_claude_ready(
        surface_ref="surface:6",
        project_key="project-key",
        spawn_time=spawn_time,
        claude_projects_dir=tmp_path / ".claude" / "projects",
        multiplexer=fake_mux,
        timeout_s=2.0,
        poll_interval_s=0.01,
    )
    elapsed = time.monotonic() - start

    t.join(timeout=1.0)
    # Must return quickly — the file appeared after 50ms.
    assert elapsed < 1.0


def test_wait_does_not_raise_when_session_file_present(tmp_path):
    from atdd.coach.commands.spawn import _wait_for_claude_ready, WorkerReadinessTimeout

    project_dir = tmp_path / ".claude" / "projects" / "pk"
    project_dir.mkdir(parents=True)
    (project_dir / "uuid.jsonl").write_text("{}")

    _wait_for_claude_ready(
        surface_ref="surface:1",
        project_key="pk",
        spawn_time=time.time(),
        claude_projects_dir=tmp_path / ".claude" / "projects",
        multiplexer=_FakeMux(),
        timeout_s=2.0,
        poll_interval_s=0.01,
    )
