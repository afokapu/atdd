# URN: component:coach-drives-lifecycle:coach-cold-start-wiring:test_coach_watcher_runtime_dir:backend:tests
# Runtime: python
# Purpose: #708 link 3 — coach RuntimeWatcher scans the persona's worktree runtime, not coach cwd.

"""Regression tests for #708 link 3 — `_watcher_runtime_dir`.

A dispatched persona runs inside the issue's worktree and writes its runtime
artifacts to `<worktree>/.atdd/runtime`. The coach's `RuntimeWatcher` must
scan there — not the coach process's cwd runtime — or it never observes a
persona event and the coach never advances past the first phase.

Scope: this covers link 3 only. Links 1 (commit `Issue`/`Phase` trailers) and
2 (per-persona git_watcher emitting `commit_observed`) remain on #708.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.coach import _watcher_runtime_dir

pytestmark = [pytest.mark.platform]


class _Ctx:
    """Minimal stand-in — `_watcher_runtime_dir` only needs `issue_number`."""

    def __init__(self, issue_number: int) -> None:
        self.issue_number = issue_number


def test_watcher_runtime_dir_points_at_worktree(monkeypatch, tmp_path):
    """The watcher runtime dir resolves to <worktree>/.atdd/runtime."""
    worktree = tmp_path / "feat-hermetic-integration"
    monkeypatch.setattr(
        "atdd.coach.handlers.spawn._resolve_worktree",
        lambda ctx: worktree,
    )

    result = _watcher_runtime_dir(_Ctx(690), fallback=tmp_path / "coach-cwd-runtime")

    assert result == worktree / ".atdd" / "runtime"
    # Crucially: NOT the coach-cwd fallback — that is the #708 bug.
    assert result != tmp_path / "coach-cwd-runtime"


def test_watcher_runtime_dir_falls_back_on_resolution_failure(monkeypatch, tmp_path):
    """When the worktree cannot be resolved, fall back to the coach runtime
    dir rather than crash the event loop."""

    def _boom(ctx):
        raise RuntimeError("no branch metadata")

    monkeypatch.setattr("atdd.coach.handlers.spawn._resolve_worktree", _boom)
    fallback = tmp_path / "coach-runtime"

    result = _watcher_runtime_dir(_Ctx(690), fallback=fallback)

    assert result == fallback
