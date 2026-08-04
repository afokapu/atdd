# URN: test:drive-state-machine:coach-state-machine-and-runtime:R001-INTEGRATION-003-watcher-reconstruct
# Acceptance: acc:drive-state-machine:R001-INTEGRATION-003-watcher-reconstruct
# WMBT: wmbt:drive-state-machine:R001
# Phase: RED
# Layer: integration
"""R001-INTEGRATION-003 — Resume reattaches the runtime watcher and
preserves the event-semantics replay contract.

Per `event-semantics.md` (#483):
- events whose handlers already completed (visible via
  `decisions.jsonl`) are NOT re-emitted on resume;
- events that occurred during the kill window but whose handlers had
  not run are delivered now;
- the single coach event queue receives each event exactly once.

The resume runner is responsible for hydrating the watcher's "handled"
set from the durable decision log before calling
``replay_from_disk()``, then emitting the queued events to whatever
consumer the runner is driving.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

# #1619: the resume walk now consults the enforcing transition gate, and
# PLANNED->RED is gated by DEFAULT_GATED_TRANSITIONS. These tests are about
# resume DURABILITY and idempotency, not about gates, so they declare their gate
# posture explicitly rather than depending on whatever config the cwd happens to
# carry. Pinning `worktree` to the test's own tmp tree matters just as much: left
# to its default the token lookup resolves up to the REAL shared Control Root.
_UNGATED_FOR_DURABILITY = {"gate": {"transitions": {"PLANNED->RED": False}}}



def _agent_dir(runtime_dir: Path, agent_id: str) -> Path:
    d = runtime_dir / "agents" / agent_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _seed_events(agent_dir: Path, events: list[dict]) -> None:
    path = agent_dir / "events.jsonl"
    with path.open("a") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def _seed_decision(writer, *, run_id: str, decision_id: str,
                   issue: int, dtype: str, inputs: dict, outcome: dict,
                   ts: str = "2026-05-09T13:00:00Z") -> None:
    writer.append({
        "decision_id": decision_id,
        "timestamp": ts,
        "coach_run_id": run_id,
        "issue_number": issue,
        "decision_type": dtype,
        "inputs": inputs,
        "outcome": outcome,
    })


def test_watcher_reattaches_with_queue_and_event_stream(tmp_path):
    """ResumeRunner.attach_watchers() returns a started RuntimeWatcher
    bound to a CoachEventQueue and replays from on-disk state."""
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    runtime = tmp_path
    agent_dir = _agent_dir(runtime, "agent-r001")
    _seed_events(agent_dir, [
        {
            "event_type": "commit_observed",
            "agent_id": "agent-r001",
            "timestamp": "2026-05-09T14:00:00Z",
            "payload": {"sha": "deadbeef", "branch": "feat/foo",
                        "worktree_path": "/x"},
        },
    ])

    writer = DecisionWriter(runtime_dir=runtime)

    runner = ResumeRunner(
        runtime_dir=runtime,
        worktree=runtime,
        gate_config=_UNGATED_FOR_DURABILITY,
        run_id="run-r001-watch-1",
        decision_writer=writer,
    )
    queue, watcher = runner.attach_watchers()
    try:
        events = queue.drain()
        commit_events = [e for e in events if e["event_type"] == "commit_observed"]
        assert len(commit_events) == 1, (
            f"reattachment must replay unhandled cached events; got "
            f"{len(commit_events)}"
        )
        assert commit_events[0]["payload"]["sha"] == "deadbeef"
    finally:
        watcher.stop()


def test_handled_events_not_re_emitted(tmp_path):
    """Events whose handlers already completed (visible in
    decisions.jsonl) are NOT re-emitted on resume.

    The resume runner inspects decision records and marks the matching
    natural-key entries on the watcher BEFORE replay_from_disk(). The
    queue therefore does not see the handled event.
    """
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    runtime = tmp_path
    agent_dir = _agent_dir(runtime, "agent-r001-handled")
    _seed_events(agent_dir, [
        {
            "event_type": "commit_observed",
            "agent_id": "agent-r001-handled",
            "timestamp": "2026-05-09T14:00:00Z",
            "payload": {"sha": "handled-sha", "branch": "feat/handled",
                        "worktree_path": "/x"},
        },
        {
            "event_type": "commit_observed",
            "agent_id": "agent-r001-handled",
            "timestamp": "2026-05-09T14:05:00Z",
            "payload": {"sha": "pending-sha", "branch": "feat/pending",
                        "worktree_path": "/x"},
        },
    ])

    writer = DecisionWriter(runtime_dir=runtime)
    run_id = "run-r001-watch-2"
    # The handler for `handled-sha` already completed and produced a
    # decision; the runner must consult this and suppress the replay
    # of that event.
    _seed_decision(writer, run_id=run_id,
                   decision_id=f"{run_id}:agent-r001-handled:commit-handled-sha",
                   issue=358, dtype="commit-observed",
                   inputs={"sha": "handled-sha",
                           "agent_id": "agent-r001-handled"},
                   outcome={"handled": True, "sha": "handled-sha"})

    runner = ResumeRunner(
        runtime_dir=runtime,
        worktree=runtime,
        gate_config=_UNGATED_FOR_DURABILITY,
        run_id=run_id,
        decision_writer=writer,
    )
    queue, watcher = runner.attach_watchers()
    try:
        commit_events = [e for e in queue.drain()
                         if e["event_type"] == "commit_observed"]
        shas = [e["payload"]["sha"] for e in commit_events]
        assert "handled-sha" not in shas, (
            f"already-handled event was re-emitted on resume; got {shas}"
        )
        assert "pending-sha" in shas, (
            f"unhandled cached event must be delivered on resume; got {shas}"
        )
    finally:
        watcher.stop()


def test_each_event_arrives_exactly_once(tmp_path):
    """The single coach event queue receives each event exactly once
    per its natural-key contract — duplicate replay emissions collapse
    to one consumer-visible event."""
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    runtime = tmp_path
    agent_dir = _agent_dir(runtime, "agent-r001-dedup")
    _seed_events(agent_dir, [
        {
            "event_type": "commit_observed",
            "agent_id": "agent-r001-dedup",
            "timestamp": "2026-05-09T14:00:00Z",
            "payload": {"sha": "abc", "branch": "feat/x",
                        "worktree_path": "/x"},
        },
        # Duplicate emission with same natural-key (payload.sha).
        {
            "event_type": "commit_observed",
            "agent_id": "agent-r001-dedup",
            "timestamp": "2026-05-09T14:01:00Z",
            "payload": {"sha": "abc", "branch": "feat/x",
                        "worktree_path": "/x"},
        },
    ])

    writer = DecisionWriter(runtime_dir=runtime)
    runner = ResumeRunner(
        runtime_dir=runtime,
        worktree=runtime,
        gate_config=_UNGATED_FOR_DURABILITY,
        run_id="run-r001-watch-3",
        decision_writer=writer,
    )
    queue, watcher = runner.attach_watchers()
    try:
        commit_events = [e for e in queue.drain()
                         if e["event_type"] == "commit_observed"]
        assert len(commit_events) == 1, (
            f"natural-key dedup must collapse duplicate emissions; "
            f"got {len(commit_events)}"
        )
    finally:
        watcher.stop()
