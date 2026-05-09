# URN: test:drive-state-machine:coach-state-machine-and-runtime:M001-INTEGRATION-002-git-watcher-commit-observed
# Acceptance: acc:drive-state-machine:M001-INTEGRATION-002-git-watcher-commit-observed
# WMBT: wmbt:drive-state-machine:M001
# Phase: RED
# Layer: integration
"""M001-INTEGRATION-002 — the git watcher emits ``commit_observed`` for
each new commit on a worktree's HEAD, with parsed commit trailers
(``Agent-Id``, ``Issue``, ``WMBT-Urn``, ``Phase``) per spec §6.4 step 1.
PR-state changes go through ``gh pr view`` polling and emit
``pr_opened`` / ``pr_closed`` per ``event-semantics.md``.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _git(args: list[str], cwd: Path) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def _bootstrap_worktree(repo_root: Path) -> Path:
    repo_root.mkdir(parents=True, exist_ok=True)
    _git(["init", "-b", "main"], repo_root)
    _git(["config", "user.email", "j5-test@atdd.local"], repo_root)
    _git(["config", "user.name", "j5-test"], repo_root)
    (repo_root / "README.md").write_text("seed\n")
    _git(["add", "."], repo_root)
    _git(["commit", "-m", "initial"], repo_root)
    return repo_root


def test_parse_commit_trailers_extracts_atdd_metadata():
    from atdd.coach.commands.watchers import parse_commit_trailers

    msg = (
        "feat(coach): wire git watcher\n\n"
        "Body paragraph that should be ignored.\n\n"
        "Agent-Id: agent-J5\n"
        "Issue: 510\n"
        "WMBT-Urn: wmbt:drive-state-machine:M001\n"
        "Phase: GREEN\n"
    )
    trailers = parse_commit_trailers(msg)
    assert trailers["Agent-Id"] == "agent-J5"
    assert trailers["Issue"] == "510"
    assert trailers["WMBT-Urn"] == "wmbt:drive-state-machine:M001"
    assert trailers["Phase"] == "GREEN"


def test_new_commit_emits_commit_observed_event(tmp_path):
    """A fresh commit on the worktree branch surfaces a commit_observed
    event with new SHA, branch, worktree path, and parsed trailers."""
    from atdd.coach.commands.watchers import CoachEventQueue, GitWatcher

    repo = _bootstrap_worktree(tmp_path / "wt")
    queue = CoachEventQueue(runtime_dir=tmp_path / "runtime")
    watcher = GitWatcher(worktree_paths=[repo], queue=queue)

    watcher.scan_once()  # establish baseline
    queue.drain()

    (repo / "file.txt").write_text("change\n")
    _git(["add", "file.txt"], repo)
    _git(
        [
            "commit",
            "-m",
            "feat(j5): add file\n\nAgent-Id: agent-J5\nIssue: 510\n"
            "WMBT-Urn: wmbt:drive-state-machine:M001\nPhase: GREEN\n",
        ],
        repo,
    )
    new_sha = _git(["rev-parse", "HEAD"], repo)

    watcher.scan_once()
    events = [e for e in queue.drain() if e["event_type"] == "commit_observed"]
    assert len(events) == 1
    ev = events[0]
    assert ev["payload"]["sha"] == new_sha
    assert ev["payload"]["branch"] == "main"
    assert ev["payload"]["worktree_path"] == str(repo)
    assert ev["payload"]["trailers"]["Agent-Id"] == "agent-J5"
    assert ev["payload"]["trailers"]["Issue"] == "510"
    assert ev["payload"]["trailers"]["WMBT-Urn"] == "wmbt:drive-state-machine:M001"
    assert ev["payload"]["trailers"]["Phase"] == "GREEN"


def test_no_event_when_no_new_commit(tmp_path):
    """Idempotent: rescanning without a new commit emits no event."""
    from atdd.coach.commands.watchers import CoachEventQueue, GitWatcher

    repo = _bootstrap_worktree(tmp_path / "wt")
    queue = CoachEventQueue(runtime_dir=tmp_path / "runtime")
    watcher = GitWatcher(worktree_paths=[repo], queue=queue)

    watcher.scan_once()
    queue.drain()
    watcher.scan_once()

    assert len(queue.drain()) == 0


def test_pr_opened_event_emitted_via_gh_pr_view_poller(tmp_path):
    """The gh pr view polling surface emits pr_opened on transition to OPEN."""
    from atdd.coach.commands.watchers import CoachEventQueue, GitWatcher

    repo = _bootstrap_worktree(tmp_path / "wt")
    queue = CoachEventQueue(runtime_dir=tmp_path / "runtime")

    states: list[dict] = [
        {"state": "OPEN", "number": 999, "headRefOid": "abc123", "baseRefName": "main", "headRefName": "feat/x"},
    ]

    def fake_gh_pr_view(worktree_path: Path) -> dict | None:
        return states.pop(0) if states else None

    watcher = GitWatcher(
        worktree_paths=[repo], queue=queue, gh_pr_view=fake_gh_pr_view
    )
    watcher.scan_once()

    events = [e for e in queue.drain() if e["event_type"] == "pr_opened"]
    assert len(events) == 1
    assert events[0]["payload"]["pr_number"] == 999
    assert events[0]["payload"]["sha"] == "abc123"


def test_pr_closed_event_on_state_transition(tmp_path):
    """When gh pr view shows the PR transitioned out of OPEN, emit pr_closed."""
    from atdd.coach.commands.watchers import CoachEventQueue, GitWatcher

    repo = _bootstrap_worktree(tmp_path / "wt")
    queue = CoachEventQueue(runtime_dir=tmp_path / "runtime")

    states: list[dict] = [
        {"state": "OPEN", "number": 7, "headRefOid": "s1", "baseRefName": "main", "headRefName": "feat/y"},
        {"state": "MERGED", "number": 7, "headRefOid": "s1", "baseRefName": "main", "headRefName": "feat/y"},
    ]

    def fake_gh_pr_view(worktree_path: Path) -> dict | None:
        return states.pop(0) if states else None

    watcher = GitWatcher(
        worktree_paths=[repo], queue=queue, gh_pr_view=fake_gh_pr_view
    )
    watcher.scan_once()
    queue.drain()
    watcher.scan_once()

    events = queue.drain()
    closed = [e for e in events if e["event_type"] == "pr_closed"]
    assert len(closed) == 1
    assert closed[0]["payload"]["pr_number"] == 7
    assert closed[0]["payload"]["terminal_state"] == "MERGED"
