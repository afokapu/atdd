# URN: test:integration-hardening:coach-state-machine-and-runtime:J5-SMOKE-001-watcher-real-infrastructure
# Acceptance: acc:integration-hardening:J5-SMOKE-001-watcher-real-infrastructure
# WMBT: wmbt:drive-state-machine:M001
# Phase: SMOKE
# Layer: smoke
"""J5-SMOKE-001 — WatcherEventLoop drives a state transition via a real git
commit on a temporary git worktree (no mocks).

This verifies that the GitWatcher + WatcherEventLoop integration works
against actual subprocess calls and real filesystem state.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _bootstrap_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-b", "main"], path)
    _git(["config", "user.email", "j5-smoke@atdd.local"], path)
    _git(["config", "user.name", "j5-smoke"], path)
    (path / "README.md").write_text("seed\n")
    _git(["add", "."], path)
    _git(["commit", "-m", "initial"], path)


def test_git_commit_drives_state_via_watcher_event_loop(tmp_path):
    """End-to-end: a real git commit with Issue+Phase trailers is observed
    by GitWatcher, queued, and consumed by WatcherEventLoop to advance
    the StateMachine from RED to GREEN."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.commands.git_watcher import GitWatcher
    from atdd.coach.handlers.state_machine import Phase, initialize_state_machine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    repo = tmp_path / "wt"
    _bootstrap_repo(repo)

    runtime_dir = tmp_path / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime_dir)

    sm = initialize_state_machine(issue_number=587)
    sm.phase = Phase.RED

    git_watcher = GitWatcher(worktree_paths=[repo], queue=queue)
    git_watcher.scan_once()  # establish baseline
    queue.drain()

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=None,
        escalation_channel=None,
    )

    (repo / "work.py").write_text("x = 1\n")
    _git(["add", "work.py"], repo)
    _git(
        [
            "commit",
            "-m",
            (
                "feat(coach): complete RED phase\n\n"
                "Issue: 587\n"
                "Phase: RED\n"
            ),
        ],
        repo,
    )

    git_watcher.scan_once()

    result = loop.process_one_event(timeout=1.0)
    assert result == "applied", f"expected 'applied', got {result!r}"
    assert sm.phase is Phase.GREEN
    assert Phase.RED in sm.history


def test_runtime_watcher_drives_state_via_events_jsonl(tmp_path):
    """RuntimeWatcher observing a real events.jsonl append drives a state
    transition via WatcherEventLoop within the 1s latency budget."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import Phase, initialize_state_machine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    runtime_dir = tmp_path / "runtime"
    agent_dir = runtime_dir / "agents" / "agent-587"
    agent_dir.mkdir(parents=True)

    queue = CoachEventQueue(runtime_dir=runtime_dir)
    sm = initialize_state_machine(issue_number=587)
    sm.phase = Phase.RED

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=None,
        escalation_channel=None,
    )
    loop.start_background_watchers()

    try:
        import json
        (agent_dir / "events.jsonl").write_text(
            json.dumps({
                "event_type": "commit_observed",
                "agent_id": "agent-587",
                "timestamp": "2026-05-11T12:00:00.000000Z",
                "payload": {
                    "sha": "deadbeef",
                    "parent_sha": None,
                    "branch": "feat/587",
                    "worktree_path": str(tmp_path / "wt"),
                    "author": "agent <agent@atdd>",
                    "trailers": {"Issue": "587", "Phase": "RED"},
                },
            }) + "\n"
        )
        deadline = time.monotonic() + 2.0
        applied = False
        while time.monotonic() < deadline:
            result = loop.process_one_event(timeout=0.2)
            if result == "applied":
                applied = True
                break
    finally:
        loop.shutdown()

    assert applied, "RuntimeWatcher did not surface a commit_observed event within 2s"
    assert sm.phase is Phase.GREEN
