# URN: test:spawn-agents:coach-spawn-rename-enter-races-text-send:E012-UNIT-004-orphan-pane-closed-on-readiness-timeout
# Acceptance: acc:spawn-agents:E012-UNIT-004-orphan-pane-closed-on-readiness-timeout
# WMBT: wmbt:spawn-agents:E012
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E012-UNIT-004 — _close_surface_on_failure is called when WorkerReadinessTimeout
fires from _wait_for_claude_ready so no orphan pane survives a failed spawn.

RED: spawn.py currently catches WorkerReadinessTimeout from _wait_for_claude_ready
(L949) and re-raises WITHOUT calling _close_surface_on_failure — only the
apply_canonical_name_and_layout failure path (L908-910) closes the surface.
A failed _wait_for_claude_ready therefore strands a live cmux pane with Claude
running and '/rename X' stuck in the input buffer (issue #811). The fix must add
_close_surface_on_failure to every WorkerReadinessTimeout raise site.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.multiplexer import FakeMultiplexer


def _make_timeout_mux(canonical_name: str, projects_dir) -> FakeMultiplexer:
    """FakeMultiplexer that succeeds the rename stage (canonical name in pane
    immediately) but whose session .jsonl never appears — _wait_for_claude_ready
    times out because no session file is written under claude_projects_dir.
    The test separately monkeypatches ATDD_CLAUDE_PROJECTS_DIR to an empty dir.
    """
    mux = FakeMultiplexer()
    # Script enough captures for:
    # 1. apply_canonical_name_and_layout verify (rename-accepted) → succeeds
    # The session-file polling in _wait_for_claude_ready is filesystem-based,
    # not pane-based, so we don't need to script captures for that stage.
    mux._pane_captures = [f"Session renamed to: {canonical_name}"] * 50
    return mux


def test_close_surface_called_when_wait_for_claude_ready_times_out(tmp_path, monkeypatch):
    """_close_surface_on_failure(surface_ref) is called when _wait_for_claude_ready
    raises WorkerReadinessTimeout, and the timeout still propagates."""
    from atdd.coach.commands.spawn import WorkerReadinessTimeout, cmd_spawn

    # Short readiness timeout so _wait_for_claude_ready fails quickly.
    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "0.1")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.02")

    worktree = tmp_path / "issue-811"
    worktree.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    # Empty claude_json and projects dir — no session file will be found.
    claude_json = tmp_path / ".claude.json"
    monkeypatch.setenv("ATDD_CLAUDE_JSON_PATH", str(claude_json))

    claude_projects = tmp_path / ".claude" / "projects"
    claude_projects.mkdir(parents=True)
    monkeypatch.setenv("ATDD_CLAUDE_PROJECTS_DIR", str(claude_projects))

    # Prompt file must exist for cmd_spawn to proceed past setup.
    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.write_text("You are the planner agent for issue #811.\n")

    # FakeMultiplexer scripted so rename-accepted gate passes but no session jsonl appears.
    from atdd.coach.utils.session_naming_apply import _claude_project_key
    canonical_name = "ATDD811"
    mux = FakeMultiplexer()
    # Enough captures for the rename-accepted verify stage to pass.
    mux._pane_captures = [f"Session renamed to: {canonical_name}"] * 100

    with pytest.raises(WorkerReadinessTimeout):
        cmd_spawn(
            persona="planner",
            llm="claude-code",
            worktree=worktree,
            issue=811,
            agent_id="planner-811-e012-test",
            runtime_root=runtime,
            multiplexer=mux,
        )

    # _close_surface_on_failure must have been called for the surface created
    # by new_surface — a 'close' op must appear in mux.calls.
    surface_refs = [c["ref"] for c in mux.calls if c.get("op") == "new_surface"]
    close_refs = [c["ref"] for c in mux.calls if c.get("op") == "close"]

    assert surface_refs, "new_surface was never called — test setup may be wrong"
    assert close_refs, (
        "_close_surface_on_failure was NOT called after WorkerReadinessTimeout "
        "from _wait_for_claude_ready; orphan pane cleanup is missing (E012, issue #811)"
    )
    assert surface_refs[0] in close_refs, (
        f"The surface {surface_refs[0]!r} created by new_surface was not closed; "
        f"close was called for: {close_refs}"
    )


def test_worker_readiness_timeout_still_propagates_after_close(tmp_path, monkeypatch):
    """WorkerReadinessTimeout propagates to the caller even after surface cleanup."""
    from atdd.coach.commands.spawn import WorkerReadinessTimeout, cmd_spawn

    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "0.1")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.02")

    worktree = tmp_path / "issue-811b"
    worktree.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    claude_json = tmp_path / ".claude.json"
    monkeypatch.setenv("ATDD_CLAUDE_JSON_PATH", str(claude_json))
    claude_projects = tmp_path / ".claude" / "projects"
    claude_projects.mkdir(parents=True)
    monkeypatch.setenv("ATDD_CLAUDE_PROJECTS_DIR", str(claude_projects))

    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.write_text("You are the planner agent for issue #811.\n")

    mux = FakeMultiplexer()
    mux._pane_captures = ["Session renamed to: ATDD811"] * 100

    # The timeout must propagate — cmd_spawn must NOT swallow it.
    with pytest.raises(WorkerReadinessTimeout):
        cmd_spawn(
            persona="planner",
            llm="claude-code",
            worktree=worktree,
            issue=811,
            agent_id="planner-811-e012-test-b",
            runtime_root=runtime,
            multiplexer=mux,
        )
