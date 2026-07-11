# URN: test:project-shared-state:verify-projection-canonicality:C002-SMOKE-001-ci-job-blocks-noncanonical-push
# Acceptance: acc:project-shared-state:C002-SMOKE-001-ci-job-blocks-noncanonical-push
# WMBT: wmbt:project-shared-state:C002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the wired canonical-projection CI job, run against a real checkout pushed to a bare git remote with no GitHub API reachable, exits non-zero and names the hand-edited file, and exits zero on a branch whose projection project(store) produced. Refs #1433.
"""SMOKE — the CI job blocks a non-canonical projection (C002-SMOKE-001).

wagon: project-shared-state | feature: verify-projection-canonicality | phase: SMOKE
WMBT: wmbt:project-shared-state:C002

The gate is only real if the *wired job* runs it, so this test does not invent a
command: it reads the canonicality step straight out of
``.github/workflows/atdd-projection-canonicality.yml`` and executes that. The remote
is a bare git repo and the environment carries no GitHub credentials — if anything
on this path reached for the API, the run would not merely fail, it could not run at
all. Refs #1433 / #1400.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from ._live import atdd_state, make_checkout

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SRC = _REPO_ROOT / "src"
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "atdd-projection-canonicality.yml"


def _wired_gate_command() -> list:
    """The command the CI job actually runs, read out of the workflow definition."""
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["canonicality"]["steps"]
    run = next(s["run"] for s in steps if "canonicality" in str(s.get("run", "")))
    # `atdd state canonicality` → the installed-form module invocation, so the job's
    # command drives THIS working copy rather than whatever is on the runner's PATH.
    assert run.split() == ["atdd", "state", "canonicality"], run
    return [sys.executable, "-m", "atdd", "state", "canonicality"]


def _run_gate(checkout: Path) -> subprocess.CompletedProcess:
    """Run the wired CI job's command in ``checkout`` with NO GitHub API reachable."""
    env = {
        "PYTHONPATH": str(_SRC),
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(checkout),
        "CI": "true",
    }  # deliberately no GH_TOKEN / GITHUB_TOKEN: the gate must not need one.
    return subprocess.run(
        _wired_gate_command(), cwd=str(checkout), env=env,
        capture_output=True, text=True, timeout=120,
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "atdd", "GIT_AUTHOR_EMAIL": "atdd@example.invalid",
             "GIT_COMMITTER_NAME": "atdd", "GIT_COMMITTER_EMAIL": "atdd@example.invalid"},
    )


def test_c002_smoke_001_ci_job_blocks_noncanonical_push(tmp_path) -> None:
    """The wired job exits zero on a projected branch and non-zero on a hand-edited one."""
    # A BARE git remote — not GitHub. Collaboration travels through git alone.
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "--quiet", str(remote)],
                   check=True, capture_output=True)

    checkout = make_checkout(tmp_path / "checkout")
    _git(checkout, "remote", "add", "origin", str(remote))
    assert atdd_state(checkout, "init").returncode == 0

    created = atdd_state(checkout, "object", "create", "--slug", "feature-x",
                         "--owner", "dev-a", "--body", "canonical body")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip()

    # Commit + push a projection that project(store) produced.
    projected = atdd_state(checkout, "project")
    assert projected.returncode == 0, projected.stderr
    projection = checkout / ".atdd" / "state" / "projection"
    assert (projection / f"{uid}.yaml").is_file()
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-q", "-m", "projection")
    _git(checkout, "push", "-q", "origin", "HEAD:refs/heads/main")

    # The same job exits zero on a branch whose projection was produced by project(store).
    clean = _run_gate(checkout)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "canonical" in clean.stdout

    # Now hand-edit the committed projection into non-canonical bytes and push that.
    offender = projection / f"{uid}.yaml"
    lines = offender.read_text(encoding="utf-8").splitlines(keepends=True)
    uid_line = next(line for line in lines if line.startswith("uid:"))
    offender.write_text(uid_line + "".join(l for l in lines if l is not uid_line),
                        encoding="utf-8")
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-q", "-m", "hand-edited projection")
    _git(checkout, "push", "-q", "origin", "HEAD:refs/heads/main")

    # The job exits non-zero and names the non-canonical file.
    blocked = _run_gate(checkout)
    assert blocked.returncode != 0, blocked.stdout
    assert f"{uid}.yaml" in blocked.stdout
    assert "NOT canonical" in blocked.stdout
