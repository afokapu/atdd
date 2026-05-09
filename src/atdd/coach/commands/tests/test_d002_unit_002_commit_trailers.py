# URN: test:drive-state-machine:coach-state-machine-and-runtime:D002-UNIT-002-commit-trailers
# Acceptance: acc:drive-state-machine:D002-UNIT-002-commit-trailers
# WMBT: wmbt:drive-state-machine:D002
# Phase: RED
# Layer: application
"""D002-UNIT-002 — `atdd agent commit` produces a commit with the four
required trailers (`Agent-Id`, `Issue`, `WMBT-Urn`, `Phase`) per spec
§7.3, delegates the worker-state write to the existing
`atdd checkpoint` primitive, and validates `--phase` against the §4.1
RED|GREEN|SMOKE|REFACTOR enum.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch) -> Path:
    """Initialize a tmp git repo with one initial commit, switch cwd."""
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "--quiet"], check=True, cwd=tmp_path)
    subprocess.run(
        ["git", "config", "user.email", "j2-test@example.com"],
        check=True, cwd=tmp_path,
    )
    subprocess.run(
        ["git", "config", "user.name", "J2 Test"],
        check=True, cwd=tmp_path,
    )
    seed = tmp_path / "README.md"
    seed.write_text("seed\n")
    subprocess.run(["git", "add", "README.md"], check=True, cwd=tmp_path)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "initial"],
        check=True, cwd=tmp_path,
    )
    return tmp_path


@pytest.fixture
def staged_change(git_repo: Path) -> Path:
    """Stage a tracked change so `atdd agent commit` has something to commit."""
    f = git_repo / "next.txt"
    f.write_text("hello\n")
    subprocess.run(["git", "add", "next.txt"], check=True, cwd=git_repo)
    return git_repo


def _last_commit_message(repo: Path) -> str:
    return subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        check=True, capture_output=True, text=True, cwd=repo,
    ).stdout


def _last_commit_sha(repo: Path) -> str:
    return subprocess.run(
        ["git", "log", "-1", "--pretty=%H"],
        check=True, capture_output=True, text=True, cwd=repo,
    ).stdout.strip()


# ---------------------------------------------------------------------------
# Phase enum — RED|GREEN|SMOKE|REFACTOR (§4.1 subset for agent commits)
# ---------------------------------------------------------------------------


def test_commit_phase_enum_is_red_green_smoke_refactor():
    from atdd.coach.commands import agent

    assert set(agent.COMMIT_PHASES) == {"RED", "GREEN", "SMOKE", "REFACTOR"}


@pytest.mark.parametrize(
    "phase", ["INIT", "PLANNED", "COMPLETE", "BLOCKED", "MERGED", "noise"],
)
def test_commit_rejects_non_agent_phase(staged_change: Path, phase: str):
    from atdd.coach.commands import agent

    with pytest.raises(ValueError):
        agent.cmd_commit(
            phase=phase,
            message="m",
            agent_id="agent-J2-test",
            issue=497,
            wmbt_urn="wmbt:drive-state-machine:D002",
        )


# ---------------------------------------------------------------------------
# Trailer composition — all four trailers per spec §7.3
# ---------------------------------------------------------------------------


def test_commit_message_carries_all_four_trailers(staged_change: Path):
    from atdd.coach.commands import agent

    sha = agent.cmd_commit(
        phase="RED",
        message="add D002 RED tests",
        agent_id="agent-J2-test",
        issue=497,
        wmbt_urn="wmbt:drive-state-machine:D002",
    )
    assert isinstance(sha, str) and len(sha) == 40

    msg = _last_commit_message(staged_change)
    # Subject preserved
    assert "add D002 RED tests" in msg
    # Trailers present (§7.3) — case-sensitive trailer keys
    assert "Agent-Id: agent-J2-test" in msg
    assert "Issue: 497" in msg
    assert "WMBT-Urn: wmbt:drive-state-machine:D002" in msg
    assert "Phase: RED" in msg


def test_commit_omits_wmbt_urn_when_not_provided(staged_change: Path):
    """WMBT-Urn is optional in the agent CLI signature (per issue body —
    `[--wmbt-urn <urn>]`) but the Agent-Id/Issue/Phase trio is mandatory."""
    from atdd.coach.commands import agent

    agent.cmd_commit(
        phase="GREEN",
        message="green pass",
        agent_id="agent-J2-test",
        issue=497,
    )
    msg = _last_commit_message(staged_change)
    assert "Agent-Id: agent-J2-test" in msg
    assert "Issue: 497" in msg
    assert "Phase: GREEN" in msg
    # When the caller doesn't supply a WMBT, no WMBT-Urn trailer is forged.
    assert "WMBT-Urn:" not in msg


# ---------------------------------------------------------------------------
# Delegation to `atdd checkpoint` (worker-state primitive)
# ---------------------------------------------------------------------------


def test_commit_delegates_worker_state_to_checkpoint(staged_change: Path):
    """`atdd checkpoint` writes `.atdd/worker-state-<issue>.json` — after
    `atdd agent commit` returns, the worker-state file must exist with
    the post-commit phase + sha."""
    from atdd.coach.commands import agent
    from atdd.coach.commands import checkpoint as checkpoint_mod

    sha = agent.cmd_commit(
        phase="SMOKE",
        message="smoke verify",
        agent_id="agent-J2-test",
        issue=497,
        wmbt_urn="wmbt:drive-state-machine:D002",
    )
    state_path = checkpoint_mod.checkpoint_path(497, root=staged_change)
    assert state_path.is_file(), (
        f"expected worker-state at {state_path} after agent commit"
    )
    import json

    state = json.loads(state_path.read_text())
    assert state["phase"] == "SMOKE"
    assert state["issue"] == 497
    assert state.get("last_commit") in (sha, sha[:7])


def test_commit_does_not_pass_no_verify(staged_change: Path, monkeypatch):
    """Pre-commit hook must still run — `atdd agent commit` must not pass
    `--no-verify` (or any other hook bypass) to git."""
    from atdd.coach.commands import agent

    real_run = subprocess.run
    captured: list[list[str]] = []

    def spy(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd and cmd[0] == "git":
            captured.append(list(cmd))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)

    agent.cmd_commit(
        phase="REFACTOR",
        message="refactor pass",
        agent_id="agent-J2-test",
        issue=497,
        wmbt_urn="wmbt:drive-state-machine:D002",
    )

    git_commit_calls = [c for c in captured if len(c) >= 2 and c[1] == "commit"]
    assert git_commit_calls, "expected `git commit` to be invoked"
    for call in git_commit_calls:
        assert "--no-verify" not in call
        assert "-n" not in call
