# URN: test:spawn-agents:L004-UNIT-002-regression-old-jsonl-boot-wait-would-have-deadlocked
# Acceptance: acc:spawn-agents:L004-UNIT-002-regression-old-jsonl-boot-wait-would-have-deadlocked
# WMBT: wmbt:spawn-agents:L004
# Phase: GREEN
# Layer: backend.unit
# Runtime: python
# Assertion: behavioral
"""L004-UNIT-002 — Negative regression: old JSONL-based boot wait would have deadlocked in lazy-session scenario

This test ALWAYS PASSES once implemented — it is a negative regression that documents the deadlock
the fix resolves. In the lazy-JSONL scenario, _wait_for_claude_ready raises WorkerReadinessTimeout
because the JSONL is not yet written at boot time. The test confirms this failure mode so any
future regression back to JSONL-based boot detection fails at SMOKE phase instead.
"""
from __future__ import annotations

import pytest


def test_regression_old_jsonl_boot_wait_would_have_deadlocked(tmp_path, monkeypatch):
    """_wait_for_claude_ready deadlocks (raises WorkerReadinessTimeout) in lazy-JSONL scenario.

    Confirms that the old JSONL-based boot wait would have blocked in the exact scenario
    that E022/E023 fixes: TUI ready ('❯' visible), but NO JSONL at boot time.
    """
    from atdd.coach.commands.spawn import WorkerReadinessTimeout, _wait_for_claude_ready

    # Short timeout so the test completes quickly
    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "0.05")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.01")

    worktree = tmp_path / "issue-863-l003-u002"
    worktree.mkdir()

    claude_projects = tmp_path / ".claude" / "projects"
    claude_projects.mkdir(parents=True)
    monkeypatch.setenv("ATDD_CLAUDE_PROJECTS_DIR", str(claude_projects))

    from atdd.coach.utils.session_naming_apply import _claude_project_key

    project_key = _claude_project_key(worktree)
    project_dir = claude_projects / project_key
    project_dir.mkdir(parents=True, exist_ok=True)

    # KEY: NO JSONL created — this is the lazy-session scenario
    # The background thread in L004-UNIT-001 writes it post-paste; here we never write it
    # at all, simulating the old flow where the boot gate fires BEFORE paste.

    import time

    spawn_time = time.monotonic()

    with pytest.raises(WorkerReadinessTimeout) as exc_info:
        _wait_for_claude_ready(
            surface_ref="surface:L004-U002",
            project_key=project_key,
            spawn_time=spawn_time,
            timeout_s=0.05,
            poll_interval_s=0.01,
        )

    msg = str(exc_info.value)

    # Confirms the deadlock: old gate fired before paste, no JSONL → timed out
    assert "did not boot" in msg or "No session .jsonl" in msg or "surface:" in msg, (
        f"WorkerReadinessTimeout message doesn't describe boot-wait failure. Got: {msg!r}"
    )
    # The project_key must appear so the operator can diagnose which directory was checked
    assert project_key in msg or "project_key" in msg, (
        f"WorkerReadinessTimeout message should contain the project_key. Got: {msg!r}"
    )
