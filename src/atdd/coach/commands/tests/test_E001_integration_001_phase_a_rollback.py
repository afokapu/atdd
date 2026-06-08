# URN: test:drive-state-machine:two-phase-commit:E001-INTEGRATION-001-phase-a-rollback
# Acceptance: acc:drive-state-machine:E001-INTEGRATION-001-phase-a-rollback
# WMBT: wmbt:drive-state-machine:E001
# Phase: RED
# Layer: integration
"""E001-INTEGRATION-001 — Phase A rolls back created worktrees on failure.

Per spec §4.6 absorption: when coach launches multiple issues and any
worktree creation fails, every already-created worktree is removed via
``_remove_worktree`` (absorbed verbatim from
``src/atdd/coach/commands/wave_planning.py``) before exit. No partial
state persists — neither orphaned worktrees nor ``decisions.jsonl``
entries for the rolled-back creations.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _fake_create_factory(fail_for: set[int], created: list[Path]):
    """Return a fake _create_worktree that succeeds except for `fail_for`.

    The factory closes over ``created`` so tests can observe the order of
    successful creations and assert rollback parity.
    """
    import subprocess

    def _fake_create(branch: str, worktree_path: Path, *, _issue_number: int) -> None:
        if _issue_number in fail_for:
            raise subprocess.CalledProcessError(
                returncode=128,
                cmd=["git", "worktree", "add", str(worktree_path), branch],
                stderr=f"fatal: rigged failure for #{_issue_number}",
            )
        worktree_path.mkdir(parents=True, exist_ok=False)
        created.append(worktree_path)

    return _fake_create


def _fake_remove_factory(removed: list[Path]):
    def _fake_remove(worktree_path: Path) -> None:
        if worktree_path.exists():
            for child in sorted(worktree_path.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                else:
                    child.rmdir()
            worktree_path.rmdir()
        removed.append(worktree_path)

    return _fake_remove


def _make_plan(numbers: list[int]):
    from atdd.coach.commands.wave_planning import PlannedIssue

    return {
        n: PlannedIssue(
            number=n,
            title=f"issue {n}",
            body="",
            dependencies=[],
            branch=f"feat/issue-{n}",
        )
        for n in numbers
    }


def test_phase_a_rolls_back_on_failure(tmp_path, monkeypatch):
    from atdd.coach.commands import two_phase_commit
    from atdd.coach.commands.durability import DecisionWriter

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_dir = tmp_path / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)

    created: list[Path] = []
    removed: list[Path] = []
    fake_create = _fake_create_factory(fail_for={360}, created=created)
    fake_remove = _fake_remove_factory(removed=removed)

    monkeypatch.setattr(two_phase_commit, "_create_worktree_call", fake_create)
    monkeypatch.setattr(two_phase_commit, "_remove_worktree_call", fake_remove)

    plan = _make_plan([358, 359, 360])

    result = two_phase_commit.phase_a_create_worktrees(
        plan=plan,
        repo_root=repo_root,
        decision_writer=writer,
        run_id="run-test-001",
    )

    assert result.failed_issue == 360
    assert sorted(p.name for p in created) == sorted(
        Path(plan[n].worktree_path).name for n in (358, 359)
    )
    # Rollback removed every successfully-created worktree.
    assert {p.name for p in removed} == {p.name for p in created}
    for path in created:
        assert not path.exists(), f"rolled back worktree still exists: {path}"


def test_phase_a_writes_no_decisions_for_rolled_back_creations(tmp_path, monkeypatch):
    from atdd.coach.commands import two_phase_commit
    from atdd.coach.commands.durability import DecisionWriter

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_dir = tmp_path / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)

    created: list[Path] = []
    removed: list[Path] = []
    monkeypatch.setattr(
        two_phase_commit,
        "_create_worktree_call",
        _fake_create_factory(fail_for={360}, created=created),
    )
    monkeypatch.setattr(
        two_phase_commit,
        "_remove_worktree_call",
        _fake_remove_factory(removed=removed),
    )

    plan = _make_plan([358, 359, 360])

    two_phase_commit.phase_a_create_worktrees(
        plan=plan,
        repo_root=repo_root,
        decision_writer=writer,
        run_id="run-test-002",
    )

    # decisions.jsonl must not contain any worktree-create decisions for
    # the rolled-back creations: the rollback discipline is "no partial
    # state persists" per spec §4.6.
    records = _read_jsonl(writer.path)
    create_decisions = [
        r for r in records if r.get("decision_type") == "worktree-create"
    ]
    assert create_decisions == [], (
        f"worktree-create decisions persisted after rollback: {create_decisions}"
    )


def test_phase_a_does_not_write_orchestrate_state_json(tmp_path, monkeypatch):
    """Resume source replacement: coach.phase_a does NOT touch
    `.atdd/orchestrate-state.json`. That file is the legacy orchestrate
    sink and is no longer written under the J4 absorption."""
    from atdd.coach.commands import two_phase_commit
    from atdd.coach.commands.durability import DecisionWriter

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_dir = tmp_path / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)

    monkeypatch.setattr(
        two_phase_commit,
        "_create_worktree_call",
        _fake_create_factory(fail_for=set(), created=[]),
    )
    monkeypatch.setattr(
        two_phase_commit,
        "_remove_worktree_call",
        _fake_remove_factory(removed=[]),
    )

    plan = _make_plan([358, 359])
    two_phase_commit.phase_a_create_worktrees(
        plan=plan,
        repo_root=repo_root,
        decision_writer=writer,
        run_id="run-test-003",
    )

    legacy_state = repo_root / ".atdd" / "orchestrate-state.json"
    assert not legacy_state.exists(), (
        "coach must not write .atdd/orchestrate-state.json — that file is "
        "replaced by decisions.jsonl per spec §4.6"
    )
