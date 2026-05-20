# URN: test:spawn-agents:coach-spawn-rename-enter-races-text-send:E012-INTEGRATION-001-full-spawn-atomic-rename-and-orphan-cleanup
# Acceptance: acc:spawn-agents:E012-INTEGRATION-001-full-spawn-atomic-rename-and-orphan-cleanup
# WMBT: wmbt:spawn-agents:E012
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E012-INTEGRATION-001 — Full cmd_spawn integration path: atomic rename paste
lands as one input block; rename-accepted gate checks 'Session renamed to:';
WorkerReadinessTimeout from _wait_for_claude_ready triggers surface close before
propagating.

RED: Two things will fail against the current implementation (issue #811):
  (a) Happy-path: apply_canonical_name_and_layout still calls send+send_key for
      /rename and uses expect_any=(canonical_name,); the FakeMultiplexer scripted to
      return 'Session renamed to:' WILL satisfy the old gate too — but the
      paste_text assertion will FAIL because send+send_key is used, not paste_text.
  (b) Timeout-path: cmd_spawn does NOT call _close_surface_on_failure after
      _wait_for_claude_ready raises — the 'close' op assertion will FAIL.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.multiplexer import FakeMultiplexer


class _HappyPathMux(FakeMultiplexer):
    """FakeMultiplexer for the cmd_spawn happy path.

    Scripted capture progression:
      - Calls 1-N: 'Session renamed to: ATDDNNN' (rename-accepted gate)
      - Calls N+1-M: paste indicator (paste-landed gate)
      - Calls M+1+: thinking marker (prompt-submitted gate)
    """

    def __init__(self, canonical_name: str):
        super().__init__()
        self._pane_captures = (
            [f"Session renamed to: {canonical_name}"] * 10
            + ["paste again to expand · 1 line"] * 10
            + ["⏺ Thinking..."] * 20
        )


def test_happy_path_uses_paste_text_for_rename(tmp_path, monkeypatch):
    """cmd_spawn happy path: paste_text is called with '/rename <name>\\n' before
    any capture probe; agent_spawned event is written to runtime/agents/."""
    from atdd.coach.commands.spawn import cmd_spawn

    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "5.0")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.02")

    # Monkeypatch _assert_worker_processing — not under test here.
    monkeypatch.setattr("atdd.coach.commands.spawn._assert_worker_processing", lambda *a, **kw: None)

    worktree = tmp_path / "issue-811-happy"
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
    (project_dir / "uuid-811-happy.jsonl").write_text("{}")

    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.write_text("You are the planner agent for issue #811.\n")

    fake_mux = _HappyPathMux("ATDD811")

    cmd_spawn(
        persona="planner",
        llm="claude-code",
        worktree=worktree,
        issue=811,
        agent_id="planner-811-integration-happy",
        runtime_root=runtime,
        multiplexer=fake_mux,
    )

    # paste_text must have been called with the atomic rename payload (not send+send_key).
    # The rename payload is a SHORT slash command ("/rename ATDDNNN\n"), NOT the long
    # launch prompt which may also mention the canonical name as a substring.
    # We identify the rename paste by: starts with "/rename ", ends with "\n", and is
    # short (< 50 chars) — distinguishing it from the multi-kilobyte launch prompt paste.
    paste_ops = [(c["ref"], c["text"]) for c in fake_mux.calls if c.get("op") == "paste_text"]
    rename_pastes = [
        (ref, text) for ref, text in paste_ops
        if text.startswith("/rename ") and text.endswith("\n") and len(text) < 50
    ]
    assert rename_pastes, (
        "paste_text was not called with an atomic '/rename ...<newline>' payload; "
        "apply_canonical_name_and_layout must use paste_text(ref, '/rename ATDDNNN\\n') "
        "instead of send+send_key for atomic rename injection (E012, issue #811). "
        f"All paste_text calls: {[(r, t[:80]) for r, t in paste_ops]}"
    )

    # The rename payload must include the trailing newline (submit is part of the paste).
    for _ref, text in rename_pastes:
        assert text.endswith("\n"), (
            f"paste_text rename payload {text!r} does not end with '\\n'"
        )

    # No standalone send() call should carry the /rename command (it is now in paste_text).
    send_rename_calls = [
        (c["ref"], c["text"]) for c in fake_mux.calls
        if c.get("op") == "send" and "/rename " in c.get("text", "")
    ]
    assert not send_rename_calls, (
        "backend.send was called with '/rename ...'; the rename must use paste_text "
        f"exclusively (E012, issue #811). Got send calls: {send_rename_calls}"
    )

    # agent_spawned event must have been written.
    agents_dir = runtime / "agents"
    assert any(agents_dir.rglob("events.jsonl")), (
        "agent_spawned event was not written to runtime/agents/ — cmd_spawn did not complete"
    )


def test_timeout_path_closes_surface_before_propagating(tmp_path, monkeypatch):
    """When _wait_for_claude_ready times out, close(surface_ref) is called and
    WorkerReadinessTimeout propagates; no agent_spawned event is written."""
    from atdd.coach.commands.spawn import WorkerReadinessTimeout, cmd_spawn

    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "0.1")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.02")

    worktree = tmp_path / "issue-811-timeout"
    worktree.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    # Empty projects dir — no session jsonl will be found.
    claude_json = tmp_path / ".claude.json"
    monkeypatch.setenv("ATDD_CLAUDE_JSON_PATH", str(claude_json))
    claude_projects = tmp_path / ".claude" / "projects"
    claude_projects.mkdir(parents=True)
    monkeypatch.setenv("ATDD_CLAUDE_PROJECTS_DIR", str(claude_projects))

    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.write_text("You are the planner agent for issue #811.\n")

    # Rename gate succeeds but _wait_for_claude_ready times out (no session jsonl).
    timeout_mux = FakeMultiplexer()
    timeout_mux._pane_captures = ["Session renamed to: ATDD811"] * 100

    with pytest.raises(WorkerReadinessTimeout):
        cmd_spawn(
            persona="planner",
            llm="claude-code",
            worktree=worktree,
            issue=811,
            agent_id="planner-811-integration-timeout",
            runtime_root=runtime,
            multiplexer=timeout_mux,
        )

    surface_refs = [c["ref"] for c in timeout_mux.calls if c.get("op") == "new_surface"]
    close_refs = [c["ref"] for c in timeout_mux.calls if c.get("op") == "close"]

    assert surface_refs, "new_surface was never called"
    assert close_refs, (
        "_close_surface_on_failure was NOT called after _wait_for_claude_ready "
        "WorkerReadinessTimeout; orphan pane cleanup is missing (E012, issue #811)"
    )
    assert surface_refs[0] in close_refs, (
        f"Surface {surface_refs[0]!r} was not cleaned up; closed: {close_refs}"
    )

    # No agent_spawned event should be written for a failed spawn.
    agents_dir = runtime / "agents"
    assert not any(agents_dir.rglob("events.jsonl")), (
        "agent_spawned was emitted despite WorkerReadinessTimeout — must not be written"
    )
