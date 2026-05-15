# URN: component:coach-drives-lifecycle:coach-cold-start-wiring:test_coach_agent_done_advance:backend:tests
# Runtime: python
# Purpose: #708 links 1+2 — coach advances on a persona's done.json via the agent_done event.

"""Regression tests for #708 links 1 & 2 — the `agent_done` advance path.

The coach's cold-start loop never advanced past the first phase: the planner
wrote `done.json` but nothing turned it into a queue event the coach consumes.
Rather than wire commit trailers (link 1) + the dead git_watcher (link 2),
the fix uses what already exists — the `RuntimeWatcher` (worktree-scoped after
link 3 / PR #709) now recognizes `done.json` and emits an `agent_done` event;
`_cold_start_proposed_transition` advances the state machine one phase on it.
The `agent_id` carries the issue, so no commit trailers are needed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.commands.coach import _cold_start_proposed_transition
from atdd.coach.commands.event_queue import CoachEventQueue
from atdd.coach.commands.runtime_watcher import RuntimeWatcher
from atdd.coach.handlers.state_machine import Phase, StateMachine

pytestmark = [pytest.mark.platform]


def _write_done(runtime: Path, agent_id: str, summary: str = "phase done") -> None:
    agent_dir = runtime / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "done.json").write_text(
        json.dumps({"timestamp": "2026-05-15T00:00:00Z", "summary": summary}),
        encoding="utf-8",
    )


# --- RuntimeWatcher: done.json -> agent_done event -------------------------


def test_runtime_watcher_emits_agent_done_for_done_json(tmp_path):
    runtime = tmp_path / ".atdd" / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime)
    watcher = RuntimeWatcher(runtime_dir=runtime, queue=queue)

    _write_done(runtime, "planner-690-5ba26310")
    emitted = watcher.scan_once()

    assert emitted >= 1
    done = [e for e in queue.drain() if e["event_type"] == "agent_done"]
    assert len(done) == 1
    assert done[0]["agent_id"] == "planner-690-5ba26310"
    assert done[0]["payload"]["source_file"] == "done.json"
    assert done[0]["payload"]["summary"] == "phase done"


def test_runtime_watcher_does_not_re_emit_unchanged_done_json(tmp_path):
    """A second scan of the same done.json must not re-fire (snapshot dedup)."""
    runtime = tmp_path / ".atdd" / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime)
    watcher = RuntimeWatcher(runtime_dir=runtime, queue=queue)

    _write_done(runtime, "planner-690-5ba26310")
    watcher.scan_once()
    queue.drain()
    assert watcher.scan_once() == 0


# --- _cold_start_proposed_transition: agent_done -> advance ----------------


def test_cold_start_advances_planned_to_red_on_agent_done():
    sm = StateMachine(issue_number=690, phase=Phase.PLANNED)
    t = _cold_start_proposed_transition(
        sm, {"event_type": "agent_done", "agent_id": "planner-690-5ba26310"}
    )
    assert t is not None
    assert t.src == Phase.PLANNED
    assert t.dst == Phase.RED


def test_cold_start_advances_red_to_green_on_agent_done():
    sm = StateMachine(issue_number=690, phase=Phase.RED)
    t = _cold_start_proposed_transition(
        sm, {"event_type": "agent_done", "agent_id": "tester-690-abc1234"}
    )
    assert t is not None and t.dst == Phase.GREEN


def test_cold_start_ignores_agent_done_for_a_different_issue():
    sm = StateMachine(issue_number=690, phase=Phase.PLANNED)
    assert _cold_start_proposed_transition(
        sm, {"event_type": "agent_done", "agent_id": "planner-999-zzz"}
    ) is None


def test_cold_start_ignores_agent_done_with_unparseable_agent_id():
    sm = StateMachine(issue_number=690, phase=Phase.PLANNED)
    assert _cold_start_proposed_transition(
        sm, {"event_type": "agent_done", "agent_id": "no-issue-number-here-xx"}
    ) is None
    assert _cold_start_proposed_transition(
        sm, {"event_type": "agent_done", "agent_id": ""}
    ) is None


def test_cold_start_non_advancing_event_still_returns_none():
    """Unrelated event types are unaffected by the agent_done branch."""
    sm = StateMachine(issue_number=690, phase=Phase.PLANNED)
    assert _cold_start_proposed_transition(
        sm, {"event_type": "heartbeat", "agent_id": "planner-690-5ba26310"}
    ) is None
