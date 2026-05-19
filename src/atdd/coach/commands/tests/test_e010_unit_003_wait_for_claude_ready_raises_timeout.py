# URN: test:spawn-agents:worker-launch-prompt-readiness-gate:E010-UNIT-003-wait-for-claude-ready-raises-timeout
# Acceptance: acc:spawn-agents:E010-UNIT-003-wait-for-claude-ready-raises-timeout
# WMBT: wmbt:spawn-agents:E010
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E010-UNIT-003 — _wait_for_claude_ready raises WorkerReadinessTimeout with
full diagnostics when the session file never appears within the bounded wait.

RED: WorkerReadinessTimeout does not exist and _wait_for_claude_ready does
not exist in spawn.py yet (issue #795).
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest


class _EmptyMux:
    """Fake multiplexer returning an empty capture — worker never came up."""

    def capture_surface_text(self, surface_ref: str) -> str:
        return ""


def test_raises_timeout_when_no_session_file(tmp_path):
    from atdd.coach.commands.spawn import _wait_for_claude_ready, WorkerReadinessTimeout

    project_dir = tmp_path / ".claude" / "projects" / "my-key"
    project_dir.mkdir(parents=True)
    # No .jsonl files created — worker never came up.

    with pytest.raises(WorkerReadinessTimeout) as exc_info:
        _wait_for_claude_ready(
            surface_ref="surface:9",
            project_key="my-key",
            spawn_time=time.time(),
            claude_projects_dir=tmp_path / ".claude" / "projects",
            multiplexer=_EmptyMux(),
            timeout_s=0.05,
            poll_interval_s=0.01,
        )

    msg = str(exc_info.value)
    assert "surface:9" in msg


def test_timeout_message_contains_elapsed_and_project_key(tmp_path):
    from atdd.coach.commands.spawn import _wait_for_claude_ready, WorkerReadinessTimeout

    project_dir = tmp_path / ".claude" / "projects" / "diag-key"
    project_dir.mkdir(parents=True)

    with pytest.raises(WorkerReadinessTimeout) as exc_info:
        _wait_for_claude_ready(
            surface_ref="surface:99",
            project_key="diag-key",
            spawn_time=time.time(),
            claude_projects_dir=tmp_path / ".claude" / "projects",
            multiplexer=_EmptyMux(),
            timeout_s=0.05,
            poll_interval_s=0.01,
        )

    msg = str(exc_info.value)
    assert "diag-key" in msg
