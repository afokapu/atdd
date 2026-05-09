# URN: test:drive-state-machine:coach-state-machine-and-runtime:D002-SMOKE-001-agent-cli-e2e
# Acceptance: acc:drive-state-machine:D002-UNIT-001-subcommands-resolve
# Acceptance: acc:drive-state-machine:D002-UNIT-002-commit-trailers
# WMBT: wmbt:drive-state-machine:D002
# Phase: SMOKE
# Layer: backend.integration
"""D002-SMOKE-001 — exercise the `atdd agent` CLI end-to-end.

Spawns the real `atdd agent` entry point (via `python3 -m atdd`) against
a tmp git repo + tmp runtime root. Verifies that the file-shape
contracts (single-doc vs jsonl, agent-dir layout) hold when the CLI
runs in its own subprocess, and that `atdd agent commit` produces a
real git commit with all four spec §7.3 trailers.

Skipped when `git` isn't on PATH (CI environments without git would
fail uninterestingly).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


SRC_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def cli_env(tmp_path: Path) -> dict[str, str]:
    """Env that points the subprocess at the local source + tmp runtime."""
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{SRC_ROOT}{os.pathsep}{existing_pp}" if existing_pp else str(SRC_ROOT)
    )
    env["ATDD_AGENT_ID"] = "agent-smoke-J2"
    env["ATDD_ISSUE"] = "497"
    env["ATDD_RUNTIME_ROOT"] = str(tmp_path / ".atdd" / "runtime")
    return env


def _run_cli(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", "-m", "atdd", "agent", *args],
        env=env, cwd=cwd, capture_output=True, text=True,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git not on PATH")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet"], check=True, cwd=repo)
    subprocess.run(["git", "config", "user.email", "j2-smoke@example.com"], check=True, cwd=repo)
    subprocess.run(["git", "config", "user.name", "J2 Smoke"], check=True, cwd=repo)
    (repo / "README.md").write_text("seed\n")
    subprocess.run(["git", "add", "README.md"], check=True, cwd=repo)
    subprocess.run(["git", "commit", "--quiet", "-m", "initial"], check=True, cwd=repo)
    return repo


# ---------------------------------------------------------------------------
# Heartbeat → events → ask → escalate → done : full agent journey
# ---------------------------------------------------------------------------


def test_smoke_full_agent_journey_via_subprocess(tmp_path: Path, cli_env: dict[str, str]):
    runtime = Path(cli_env["ATDD_RUNTIME_ROOT"])
    cwd = tmp_path

    # 1. heartbeat
    r = _run_cli(["heartbeat", "--current-step", "starting"], cli_env, cwd)
    assert r.returncode == 0, r.stderr
    hb = json.loads((runtime / "agents/agent-smoke-J2/heartbeat.json").read_text())
    assert hb["current_step"] == "starting"

    # 2. event (commit_observed with sha payload)
    r = _run_cli(
        ["event", "commit_observed", "--data", json.dumps({"sha": "deadbeef"})],
        cli_env, cwd,
    )
    assert r.returncode == 0, r.stderr
    events_path = runtime / "agents/agent-smoke-J2/events.jsonl"
    lines = [ln for ln in events_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["event_type"] == "commit_observed"
    assert parsed["agent_id"] == "agent-smoke-J2"
    assert parsed["payload"] == {"sha": "deadbeef"}

    # 3. ask
    r = _run_cli(
        ["ask", "--question", "approve refactor?", "--type", "approval"],
        cli_env, cwd,
    )
    assert r.returncode == 0, r.stderr
    questions_path = runtime / "agents/agent-smoke-J2/questions.jsonl"
    qrec = json.loads(questions_path.read_text().splitlines()[0])
    assert qrec["type"] == "approval"
    assert qrec["question"] == "approve refactor?"

    # 4. escalate
    r = _run_cli(
        ["escalate", "--reason", "doc gap", "--severity", "warn"],
        cli_env, cwd,
    )
    assert r.returncode == 0, r.stderr
    erec = json.loads(
        (runtime / "agents/agent-smoke-J2/escalations.jsonl").read_text().splitlines()[0]
    )
    assert erec["severity"] == "warn"

    # 5. done
    r = _run_cli(["done", "--summary", "smoke complete"], cli_env, cwd)
    assert r.returncode == 0, r.stderr
    done = json.loads((runtime / "agents/agent-smoke-J2/done.json").read_text())
    assert done["summary"] == "smoke complete"


# ---------------------------------------------------------------------------
# `atdd agent commit` : real git commit with all four trailers
# ---------------------------------------------------------------------------


def test_smoke_commit_produces_real_git_commit_with_trailers(
    git_repo: Path, cli_env: dict[str, str],
):
    cli_env["ATDD_RUNTIME_ROOT"] = str(git_repo / ".atdd" / "runtime")
    (git_repo / "feature.txt").write_text("payload\n")
    subprocess.run(["git", "add", "feature.txt"], check=True, cwd=git_repo)

    r = _run_cli(
        [
            "commit",
            "--phase", "RED",
            "--message", "smoke: add feature.txt",
            "--wmbt-urn", "wmbt:drive-state-machine:D002",
        ],
        cli_env, git_repo,
    )
    assert r.returncode == 0, r.stderr

    msg = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        check=True, capture_output=True, text=True, cwd=git_repo,
    ).stdout
    assert "smoke: add feature.txt" in msg
    assert "Agent-Id: agent-smoke-J2" in msg
    assert "Issue: 497" in msg
    assert "WMBT-Urn: wmbt:drive-state-machine:D002" in msg
    assert "Phase: RED" in msg

    # Worker-state checkpoint must exist (delegation to atdd checkpoint).
    state = json.loads(
        (git_repo / ".atdd" / "worker-state-497.json").read_text()
    )
    assert state["phase"] == "RED"
    assert state["issue"] == 497


def test_smoke_commit_rejects_planned_phase(
    git_repo: Path, cli_env: dict[str, str],
):
    cli_env["ATDD_RUNTIME_ROOT"] = str(git_repo / ".atdd" / "runtime")
    (git_repo / "x.txt").write_text("x\n")
    subprocess.run(["git", "add", "x.txt"], check=True, cwd=git_repo)

    r = _run_cli(
        ["commit", "--phase", "PLANNED", "--message", "noop"],
        cli_env, git_repo,
    )
    assert r.returncode != 0
    # argparse error: 'PLANNED' is not in {RED, GREEN, SMOKE, REFACTOR}
    assert "PLANNED" in (r.stderr + r.stdout)
