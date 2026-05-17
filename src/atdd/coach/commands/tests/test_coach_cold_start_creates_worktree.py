# URN: component:coach-drives-lifecycle:coach-cold-start-wiring:test_coach_cold_start_creates_worktree:backend:tests
# Runtime: python
# Phase: RED
# Layer: integration
# Purpose: coach cold-start must create the issue's git worktree before spawning the planner.

"""RED regression test — coach cold-start worktree creation.

Root-cause incident (2026-05-16): ``coach.run()`` cold-start spawned the
planner persona without ever running ``git worktree add``. The spawn
handler's ``_resolve_worktree`` only *derives* a path — nothing created
the worktree. ``commands/two_phase_commit.py::phase_a_create_worktrees``
exists but has zero callers ("not yet wired into a live command path").
Agents were therefore dispatched into bare non-git directories and would
have committed onto protected ``main``.

This pins the contract for the surgical fix: ``_ensure_issue_worktree(ctx)``
creates a real git worktree at the path the spawn handler resolves, is
idempotent, and honors ``Branch:`` issue-body metadata. The fourth test
pins that the helper is actually wired into ``_drive_single_issue`` ahead
of the planner spawn.

RED until the helper exists and is wired.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )


def _make_repo(root: Path) -> Path:
    """Create a minimal git repo at ``root/main`` and return its path."""
    repo = root / "main"
    repo.mkdir()
    _git("init", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "ATDD Test", cwd=repo)
    (repo / "README.md").write_text("seed\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "seed", cwd=repo)
    return repo


def _stub_issue(monkeypatch, *, branch_line: str = "") -> None:
    """Stub session_template.fetch_issue with an issue body."""
    from atdd.coach.commands import session_template

    body = "## Issue Metadata\n\n| Field | Value |\n|-------|-------|\n"
    if branch_line:
        body += f"| Branch | {branch_line} |\n"
    body += "\n## Summary\nregression fixture\n"
    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "fix something", "body": body},
    )


def test_ensure_worktree_creates_git_worktree_when_absent(tmp_path, monkeypatch):
    """_ensure_issue_worktree creates a real git worktree when none exists."""
    from atdd.coach.commands import coach as coach_mod
    from atdd.coach.handlers.state_machine import CoachContext

    repo = _make_repo(tmp_path)
    monkeypatch.chdir(repo)
    _stub_issue(monkeypatch)  # no Branch metadata — derive-branch fallback

    ctx = CoachContext(issue_number=4242)
    worktree = coach_mod._ensure_issue_worktree(ctx)

    assert worktree is not None, "expected a worktree path, got None"
    assert worktree == tmp_path / "issue-4242"
    assert (worktree / ".git").exists(), f"{worktree} is not a git worktree"
    listed = subprocess.run(
        ["git", "worktree", "list"], cwd=str(repo), capture_output=True, text=True
    ).stdout
    assert str(worktree) in listed, f"git does not list {worktree}:\n{listed}"


def test_ensure_worktree_is_idempotent(tmp_path, monkeypatch):
    """A second call is a no-op that returns the same path without raising."""
    from atdd.coach.commands import coach as coach_mod
    from atdd.coach.handlers.state_machine import CoachContext

    repo = _make_repo(tmp_path)
    monkeypatch.chdir(repo)
    _stub_issue(monkeypatch)

    ctx = CoachContext(issue_number=4242)
    first = coach_mod._ensure_issue_worktree(ctx)
    second = coach_mod._ensure_issue_worktree(ctx)

    assert first == second
    assert second is not None and (second / ".git").exists()


def test_ensure_worktree_honors_branch_metadata(tmp_path, monkeypatch):
    """When the issue body declares Branch:, the worktree path derives from it."""
    from atdd.coach.commands import coach as coach_mod
    from atdd.coach.handlers.state_machine import CoachContext

    repo = _make_repo(tmp_path)
    monkeypatch.chdir(repo)
    _stub_issue(monkeypatch, branch_line="`feat/my-thing`")

    ctx = CoachContext(issue_number=4242)
    worktree = coach_mod._ensure_issue_worktree(ctx)

    assert worktree == tmp_path / "feat-my-thing"
    assert worktree is not None and (worktree / ".git").exists()


def test_drive_single_issue_ensures_worktree_before_spawn(tmp_path, monkeypatch):
    """_drive_single_issue calls _ensure_issue_worktree before the planner spawn."""
    from atdd.coach.commands import coach as coach_mod
    from atdd.coach.handlers.state_machine import HandlerResult, Phase

    repo = _make_repo(tmp_path)
    monkeypatch.chdir(repo)
    _stub_issue(monkeypatch)

    order: list[str] = []

    def _spy_ensure(ctx):
        order.append("ensure-worktree")
        return tmp_path / "issue-4242"

    def _spy_spawn(ctx, transition):
        order.append("spawn")
        return HandlerResult.HANDLED

    monkeypatch.setattr(coach_mod, "_ensure_issue_worktree", _spy_ensure)

    rc = coach_mod.run(
        issue_numbers=[4242],
        dry_run=False,
        resume=None,
        _runtime_dir_override=tmp_path / ".atdd" / "runtime",
        _max_loop_events=0,
        _spawn_func=_spy_spawn,
    )

    assert rc == 0
    assert order == ["ensure-worktree", "spawn"], (
        f"worktree must be ensured before spawn; got {order}"
    )
