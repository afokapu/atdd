# URN: test:drive-state-machine:two-phase-commit:E001-INTEGRATION-003-resume-source-replaced
# Acceptance: acc:drive-state-machine:E001-INTEGRATION-003-resume-source-replaced
# WMBT: wmbt:drive-state-machine:E001
# Phase: RED
# Layer: integration
"""E001-INTEGRATION-003 — decisions.jsonl replaces orchestrate-state.json
as the durable resume source.

Per spec §4.6: ``--resume`` reads ``decisions.jsonl``, recognizes
already-created worktrees as no-ops (idempotent ``_create_worktree``
short-circuits), recognizes already-launched sessions (idempotent spawn
check), and only re-launches the un-launched siblings.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.utils.multiplexer import (
    MultiplexerBackend,
    MultiplexerRef,
)

pytestmark = [pytest.mark.platform]


class _RecordingBackend(MultiplexerBackend):
    name = "recording"

    def __init__(self):
        self.dispatched: list[dict] = []

    def new_workspace(self, cwd: str, command: str, name=None) -> MultiplexerRef:
        ref = f"workspace:{len(self.dispatched) + 1}"
        self.dispatched.append({"cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

    def read_screen(self, ref, lines=50):
        return ""

    def send(self, ref, text):
        pass

    def send_key(self, ref, key):
        pass

    def list_workspaces(self):
        return []

    def close(self, ref):
        pass


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _make_plan(numbers: list[int]):
    from atdd.coach.commands.orchestrate import PlannedIssue

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


def _seed_worktrees(plan, repo_root: Path) -> None:
    for num, issue in plan.items():
        wt = repo_root.parent / f"feat-issue-{num}"
        wt.mkdir(parents=True, exist_ok=True)
        issue.worktree_path = str(wt)


def test_resume_skips_already_launched_sessions(tmp_path):
    """Pre-seed decisions.jsonl as if 358 already launched. Only 359 and
    360 are dispatched in the resumed run."""
    from atdd.coach.commands import two_phase_commit
    from atdd.coach.commands.durability import DecisionWriter

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_dir = tmp_path / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)

    # Pre-seed: simulate that the prior run got worktrees + 358's launch
    # durably written. The decision id encodes (run-id, issue, kind).
    pre_run_id = "run-test-200"
    for num in (358, 359, 360):
        writer.append({
            "decision_id": f"{pre_run_id}:#{num}:worktree-create",
            "timestamp": "2026-05-09T13:00:00Z",
            "coach_run_id": pre_run_id,
            "issue_number": num,
            "decision_type": "worktree-create",
            "inputs": {"branch": f"feat/issue-{num}"},
            "outcome": {"created": True},
        })
    writer.append({
        "decision_id": f"{pre_run_id}:#358:agent-spawn",
        "timestamp": "2026-05-09T13:01:00Z",
        "coach_run_id": pre_run_id,
        "issue_number": 358,
        "decision_type": "agent-spawn",
        "inputs": {"branch": "feat/issue-358"},
        "outcome": {"launched": True, "ref": "workspace:1"},
    })

    plan = _make_plan([358, 359, 360])
    _seed_worktrees(plan, repo_root)

    backend = _RecordingBackend()
    result = two_phase_commit.phase_b_launch_sessions(
        plan=plan,
        repo_root=repo_root,
        backend=backend,
        decision_writer=writer,
        run_id=pre_run_id,
    )

    # Only 359 and 360 are newly launched. 358 is recognized as already
    # launched and skipped.
    assert sorted(result.launched_issues) == [359, 360]
    assert sorted(d["name"] for d in backend.dispatched if d.get("name")) == sorted(
        d["name"] for d in backend.dispatched if d.get("name") and "358" not in d["name"]
    ), "no dispatch should have happened for #358"
    dispatched_branches = [d["cwd"] for d in backend.dispatched]
    assert all("feat-issue-358" not in cwd for cwd in dispatched_branches)


def test_resume_skips_already_created_worktrees(tmp_path, monkeypatch):
    """Phase A is idempotent on resume: pre-seeded
    ``worktree-create`` decisions short-circuit the create call."""
    from atdd.coach.commands import two_phase_commit
    from atdd.coach.commands.durability import DecisionWriter

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_dir = tmp_path / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)

    pre_run_id = "run-test-201"
    # Only 358's worktree is recorded as created.
    writer.append({
        "decision_id": f"{pre_run_id}:#358:worktree-create",
        "timestamp": "2026-05-09T13:00:00Z",
        "coach_run_id": pre_run_id,
        "issue_number": 358,
        "decision_type": "worktree-create",
        "inputs": {"branch": "feat/issue-358"},
        "outcome": {"created": True},
    })

    create_calls: list[int] = []
    removed: list[Path] = []

    def fake_create(branch: str, worktree_path: Path, *, _issue_number: int) -> None:
        create_calls.append(_issue_number)
        worktree_path.mkdir(parents=True, exist_ok=False)

    def fake_remove(worktree_path: Path) -> None:
        removed.append(worktree_path)

    monkeypatch.setattr(two_phase_commit, "_create_worktree_call", fake_create)
    monkeypatch.setattr(two_phase_commit, "_remove_worktree_call", fake_remove)

    plan = _make_plan([358, 359])

    result = two_phase_commit.phase_a_create_worktrees(
        plan=plan,
        repo_root=repo_root,
        decision_writer=writer,
        run_id=pre_run_id,
    )

    # Only #359's create call was made; #358 was idempotent skipped.
    assert sorted(create_calls) == [359]
    assert result.failed_issue is None


def test_orchestrate_state_json_never_written(tmp_path):
    """The legacy state file is no longer the durable resume source.
    decisions.jsonl is canonical."""
    from atdd.coach.commands import two_phase_commit
    from atdd.coach.commands.durability import DecisionWriter

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_dir = tmp_path / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)

    plan = _make_plan([358])
    _seed_worktrees(plan, repo_root)

    backend = _RecordingBackend()
    two_phase_commit.phase_b_launch_sessions(
        plan=plan,
        repo_root=repo_root,
        backend=backend,
        decision_writer=writer,
        run_id="run-test-202",
    )

    assert not (repo_root / ".atdd" / "orchestrate-state.json").exists()
    assert writer.path.exists() and writer.path.read_text().strip(), (
        "decisions.jsonl is the new durable resume source"
    )
