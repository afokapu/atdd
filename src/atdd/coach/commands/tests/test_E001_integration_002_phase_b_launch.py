# URN: test:drive-state-machine:two-phase-commit:E001-INTEGRATION-002-phase-b-launch
# Acceptance: acc:drive-state-machine:E001-INTEGRATION-002-phase-b-launch
# WMBT: wmbt:drive-state-machine:E001
# Phase: RED
# Layer: integration
"""E001-INTEGRATION-002 — Phase B writes a decision per success and
does not roll back already-launched siblings on a peer failure.

Per spec §4.6 (asymmetric rollback): a successfully-launched agent has
spawned a process and may already be doing work; tearing it down on a
sibling's failure loses progress. ``--resume`` instead picks up the
un-launched siblings.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.utils.multiplexer import (
    MultiplexerBackend,
    MultiplexerError,
    MultiplexerRef,
)

pytestmark = [pytest.mark.platform]


class _FakeBackend(MultiplexerBackend):
    """Minimal multiplexer backend that records dispatches and can be
    rigged to fail for specific names."""

    name = "fake"

    def __init__(self, fail_names: set[str]):
        self.fail_names = fail_names
        self.dispatched: list[dict] = []
        self.closed: list[str] = []
        self.renamed: list[tuple[str, str]] = []
        self.sent: list[tuple[str, str]] = []

    def new_workspace(self, cwd: str, command: str, name=None) -> MultiplexerRef:
        if name in self.fail_names:
            raise MultiplexerError(f"rigged failure for {name}")
        ref = f"workspace:{len(self.dispatched) + 1}"
        self.dispatched.append({"cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

    def new_surface(self, **kwargs) -> MultiplexerRef:
        name = kwargs.get("name")
        if name in self.fail_names:
            raise MultiplexerError(f"rigged failure for {name}")
        ref = f"surface:{len(self.dispatched) + 1}"
        self.dispatched.append({**kwargs, "ref": ref})
        return ref

    def read_screen(self, ref, lines=50):
        return ""

    def send(self, ref, text):
        self.sent.append((ref, text))

    def send_key(self, ref, key):
        self.sent.append((ref, f"<key>{key}"))

    def list_workspaces(self):
        return [d["ref"] for d in self.dispatched if d["ref"].startswith("workspace:")]

    def close(self, ref):
        self.closed.append(ref)

    def rename(self, ref, name):
        self.renamed.append((ref, name))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _make_plan(numbers: list[int]):
    from atdd.coach.commands._archived.orchestrate import PlannedIssue

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
    """Mark Phase A as completed by populating worktree_path on each plan
    entry and creating the directory on disk."""
    for num, issue in plan.items():
        wt = repo_root.parent / f"feat-issue-{num}"
        wt.mkdir(parents=True, exist_ok=True)
        issue.worktree_path = str(wt)


def test_phase_b_writes_decision_per_successful_launch(tmp_path):
    from atdd.coach.commands import two_phase_commit
    from atdd.coach.commands.durability import DecisionWriter

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_dir = tmp_path / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)

    plan = _make_plan([358, 359])
    _seed_worktrees(plan, repo_root)

    backend = _FakeBackend(fail_names=set())

    result = two_phase_commit.phase_b_launch_sessions(
        plan=plan,
        repo_root=repo_root,
        backend=backend,
        decision_writer=writer,
        run_id="run-test-100",
    )

    assert result.launched_issues == [358, 359]
    assert result.failed_issues == []

    records = _read_jsonl(writer.path)
    spawn_records = [r for r in records if r.get("decision_type") == "agent-spawn"]
    issues = sorted(r["issue_number"] for r in spawn_records)
    assert issues == [358, 359], (
        f"expected one agent-spawn decision per success, got {spawn_records}"
    )
    for r in spawn_records:
        assert r["coach_run_id"] == "run-test-100"
        assert r["outcome"].get("launched") is True


def test_phase_b_does_not_roll_back_on_sibling_failure(tmp_path):
    from atdd.coach.commands import two_phase_commit
    from atdd.coach.commands.durability import DecisionWriter

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_dir = tmp_path / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)

    plan = _make_plan([358, 359, 360])
    _seed_worktrees(plan, repo_root)

    # Rig 360 to fail at multiplexer dispatch by name.
    fail_canonical = {f"feat-issue-360"}
    # Find canonical names by probing: backend fails on names containing "360"
    backend = _FakeBackend(fail_names=set())
    backend.fail_names = {n for n in [None] if False}  # placeholder
    # Use a lambda that matches by issue number via the command path.
    original_new_workspace = backend.new_workspace

    def selective_new_workspace(cwd, command, name=None):
        if "360" in (name or "") or "360" in command or "360" in cwd:
            raise MultiplexerError("rigged failure for 360")
        return original_new_workspace(cwd, command, name=name)

    backend.new_workspace = selective_new_workspace  # type: ignore[assignment]

    result = two_phase_commit.phase_b_launch_sessions(
        plan=plan,
        repo_root=repo_root,
        backend=backend,
        decision_writer=writer,
        run_id="run-test-101",
    )

    assert sorted(result.launched_issues) == [358, 359]
    assert result.failed_issues == [360]

    records = _read_jsonl(writer.path)
    spawn_records = [r for r in records if r.get("decision_type") == "agent-spawn"]
    spawned_issues = sorted(r["issue_number"] for r in spawn_records)
    assert spawned_issues == [358, 359], (
        f"failed launch must not retro-write or undo sibling decisions: "
        f"{spawn_records}"
    )

    # Asymmetric rollback discipline: nothing was closed on the backend.
    assert backend.closed == [], (
        "Phase B must NOT roll back already-launched siblings on a peer "
        "failure (spec §4.6)"
    )


def test_phase_b_records_partial_launch_for_resume(tmp_path):
    """The partial-launch state is durably recorded so that a subsequent
    --resume run picks up only the unlaunched siblings."""
    from atdd.coach.commands import two_phase_commit
    from atdd.coach.commands.durability import DecisionWriter

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_dir = tmp_path / "runtime"
    writer = DecisionWriter(runtime_dir=runtime_dir)

    plan = _make_plan([358, 359, 360])
    _seed_worktrees(plan, repo_root)

    backend = _FakeBackend(fail_names=set())
    original_new_workspace = backend.new_workspace

    def selective_new_workspace(cwd, command, name=None):
        if "360" in (name or "") or "360" in command or "360" in cwd:
            raise MultiplexerError("rigged failure for 360")
        return original_new_workspace(cwd, command, name=name)

    backend.new_workspace = selective_new_workspace  # type: ignore[assignment]

    two_phase_commit.phase_b_launch_sessions(
        plan=plan,
        repo_root=repo_root,
        backend=backend,
        decision_writer=writer,
        run_id="run-test-102",
    )

    records = _read_jsonl(writer.path)
    launched = {r["issue_number"] for r in records if r.get("decision_type") == "agent-spawn"}
    assert launched == {358, 359}

    # The legacy state file MUST NOT exist — decisions.jsonl is the
    # durable resume source per spec §4.6.
    legacy_state = repo_root / ".atdd" / "orchestrate-state.json"
    assert not legacy_state.exists()
