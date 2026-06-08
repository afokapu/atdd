# URN: test:drive-state-machine:two-phase-commit:E001-SMOKE-001-two-phase-commit-real-fs
# Acceptance: acc:drive-state-machine:E001-INTEGRATION-001-phase-a-rollback
# WMBT: wmbt:drive-state-machine:E001
# Phase: SMOKE
# Layer: integration
"""E001-SMOKE-001 — Two-phase commit against a real git repo + fs.

Drives ``phase_a_create_worktrees`` end-to-end against a real
``git worktree add`` (no monkeypatching of the create helper). Verifies
that the absorbed rollback discipline holds when ``git`` actually fails
(e.g. duplicated branch). The Phase B test stubs only the
multiplexer backend — the rest of the pipeline (prompt rendering,
launch script write, decisions.jsonl append) runs against real disk.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _make_repo(tmp_path: Path, *, branches: tuple[int, ...] = (358, 359, 360)) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "smoke@example.com", cwd=repo)
    _git("config", "user.name", "Smoke", cwd=repo)
    (repo / "seed.txt").write_text("seed")
    _git("add", "seed.txt", cwd=repo)
    _git("commit", "-q", "-m", "seed", cwd=repo)
    for num in branches:
        _git("branch", f"feat/issue-{num}", cwd=repo)
    return repo


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_phase_a_real_git_success_records_decisions(tmp_path, monkeypatch):
    from atdd.coach.commands import two_phase_commit
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.wave_planning import PlannedIssue

    repo = _make_repo(tmp_path)
    monkeypatch.chdir(repo)
    runtime_dir = tmp_path / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)

    plan = {
        n: PlannedIssue(number=n, branch=f"feat/issue-{n}")
        for n in (358, 359)
    }

    try:
        result = two_phase_commit.phase_a_create_worktrees(
            plan=plan,
            repo_root=repo,
            decision_writer=writer,
            run_id="smoke-A",
        )
        assert result.failed_issue is None
        # Real worktrees on disk under the parent.
        for num in (358, 359):
            wt = Path(plan[num].worktree_path)
            assert wt.exists()
            assert (wt / "seed.txt").exists()
        # Decisions written.
        records = _read_jsonl(writer.path)
        creates = [r for r in records if r["decision_type"] == "worktree-create"]
        assert sorted(r["issue_number"] for r in creates) == [358, 359]
    finally:
        # Clean up worktrees so pytest's tmp_path cleanup succeeds.
        for num in (358, 359):
            wt_path = plan[num].worktree_path
            if wt_path and Path(wt_path).exists():
                subprocess.run(
                    ["git", "worktree", "remove", "--force", wt_path],
                    cwd=str(repo),
                    check=False,
                    capture_output=True,
                )


def test_phase_a_real_git_failure_rolls_back(tmp_path, monkeypatch):
    """Force a failure by NOT creating branch ``feat/issue-360`` in the
    repo, so the real ``git worktree add`` fails with "invalid reference"
    when it reaches that issue. Phase A must roll back the prior two
    creations."""
    from atdd.coach.commands import two_phase_commit
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.wave_planning import PlannedIssue

    # Only 358 and 359 have branches; 360 will fail.
    repo = _make_repo(tmp_path, branches=(358, 359))
    monkeypatch.chdir(repo)
    runtime_dir = tmp_path / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)

    plan = {
        n: PlannedIssue(number=n, branch=f"feat/issue-{n}")
        for n in (358, 359, 360)
    }

    try:
        result = two_phase_commit.phase_a_create_worktrees(
            plan=plan,
            repo_root=repo,
            decision_writer=writer,
            run_id="smoke-A-fail",
        )
        assert result.failed_issue == 360
        # Both prior worktrees rolled back.
        for num in (358, 359):
            wt = Path(plan[num].worktree_path)
            assert not wt.exists(), f"#{num} worktree should be rolled back: {wt}"
        # No worktree-create decisions persisted.
        records = _read_jsonl(writer.path)
        creates = [r for r in records if r["decision_type"] == "worktree-create"]
        assert creates == []
    finally:
        for num in (358, 359, 360):
            wt_path = plan[num].worktree_path
            if wt_path and Path(wt_path).exists():
                subprocess.run(
                    ["git", "worktree", "remove", "--force", wt_path],
                    cwd=str(repo),
                    check=False,
                    capture_output=True,
                )
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=str(repo),
            check=False,
            capture_output=True,
        )


def test_decisions_jsonl_is_append_only_and_stays_durable(tmp_path, monkeypatch):
    """Run Phase A twice with the same run_id and confirm the second
    invocation is idempotent: no duplicate ``worktree-create`` records,
    no orphaned worktrees."""
    from atdd.coach.commands import two_phase_commit
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.wave_planning import PlannedIssue

    repo = _make_repo(tmp_path)
    monkeypatch.chdir(repo)
    runtime_dir = tmp_path / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)

    plan_first = {358: PlannedIssue(number=358, branch="feat/issue-358")}
    plan_second = {358: PlannedIssue(number=358, branch="feat/issue-358")}

    try:
        result_a = two_phase_commit.phase_a_create_worktrees(
            plan=plan_first,
            repo_root=repo,
            decision_writer=writer,
            run_id="smoke-A-replay",
        )
        assert result_a.failed_issue is None

        # Replay: same run_id, idempotent skip.
        result_b = two_phase_commit.phase_a_create_worktrees(
            plan=plan_second,
            repo_root=repo,
            decision_writer=writer,
            run_id="smoke-A-replay",
        )
        assert result_b.failed_issue is None
        assert result_b.created_paths == [], (
            "replay must not create worktrees again"
        )

        records = _read_jsonl(writer.path)
        creates = [r for r in records if r["decision_type"] == "worktree-create"]
        assert len(creates) == 1, (
            f"replay must not duplicate the worktree-create record: {creates}"
        )
    finally:
        wt_path = plan_first[358].worktree_path
        if wt_path and Path(wt_path).exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", wt_path],
                cwd=str(repo),
                check=False,
                capture_output=True,
            )
