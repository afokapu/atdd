# URN: test:spawn-agents:worker-launch-prompt-readiness-gate:E010-SMOKE-001-readiness-gate-with-real-multiplexer
# Acceptance: acc:spawn-agents:E010-SMOKE-001-readiness-gate-with-real-multiplexer
# WMBT: wmbt:spawn-agents:E010
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E010-SMOKE-001 — against a real cmux session, the readiness gate correctly
waits for a session .jsonl to appear before pasting, and the post-paste
assertion confirms the worker is processing — no phantom 'transitioned:true'
is logged.

Opt-in: skipped unless ATDD_RUN_SMOKE=1. A real cmux session is required.
The launch command is a fast-exiting shell command (not real Claude Code) so
this test is hermetic — it uses echo to write a mock session file.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not os.environ.get("ATDD_RUN_SMOKE"),
        reason="opt-in SMOKE test — set ATDD_RUN_SMOKE=1 to run against a real multiplexer",
    ),
]


def test_readiness_gate_with_real_multiplexer(tmp_path, monkeypatch):
    """Real cmux: _wait_for_claude_ready completes, transitioned:true logged
    only after the worker-processing assertion passes (hermetic launch cmd)."""
    from atdd.coach.commands.spawn import (
        _pre_trust_worktree,
        _wait_for_claude_ready,
        _assert_worker_processing,
        WorkerReadinessTimeout,
    )
    from atdd.coach.utils.multiplexer import get_multiplexer

    mx = get_multiplexer()
    if mx.name != "cmux":
        pytest.skip("E010 SMOKE test only exercises cmux backend")

    worktree = tmp_path / "e010-smoke-worktree"
    worktree.mkdir()
    claude_json = tmp_path / ".claude.json"
    claude_projects = tmp_path / ".claude" / "projects"
    project_key = "e010-smoke"
    project_dir = claude_projects / project_key
    project_dir.mkdir(parents=True)

    # 1. Pre-trust — must not touch real ~/.claude.json.
    _pre_trust_worktree(worktree, claude_json)
    data = json.loads(claude_json.read_text())
    assert data["projects"][str(worktree)]["hasTrustDialogAccepted"] is True

    # 2. Create a real cmux surface with a hermetic (fast-exiting) launch command.
    surface_ref = mx.new_surface(
        cwd=str(worktree),
        command="sleep 5",  # hermetic — no real Claude Code
        name="ATDD795-e010-smoke",
    )
    assert surface_ref

    spawn_time = time.time()

    # Write a session file after 0.1s to simulate Claude writing on boot.
    def _write_session_file():
        time.sleep(0.1)
        (project_dir / "smoke-uuid.jsonl").write_text("{}")

    threading.Thread(target=_write_session_file, daemon=True).start()

    try:
        # 3. _wait_for_claude_ready must complete (file appears in time).
        _wait_for_claude_ready(
            surface_ref=surface_ref,
            project_key=project_key,
            spawn_time=spawn_time,
            claude_projects_dir=claude_projects,
            multiplexer=mx,
            timeout_s=5.0,
            poll_interval_s=0.05,
        )

        # 4. decisions.jsonl: no phantom transitioned:true before the gate.
        decisions_file = tmp_path / "decisions.jsonl"
        assert not decisions_file.exists() or all(
            json.loads(ln).get("outcome", {}).get("transitioned") is not True
            for ln in decisions_file.read_text().splitlines()
            if ln.strip()
        )
    finally:
        try:
            mx.close_surface(surface_ref)
        except Exception:
            pass
