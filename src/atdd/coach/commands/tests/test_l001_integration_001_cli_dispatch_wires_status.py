# URN: test:drive-state-machine:coach-state-machine-and-runtime:L001-INTEGRATION-001-cli-dispatch-wires-status
# Acceptance: acc:drive-state-machine:L001-INTEGRATION-001-cli-dispatch-wires-status
# WMBT: wmbt:drive-state-machine:L001
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""`atdd coach status` is reachable via the top-level CLI dispatch and does
not break existing `atdd coach <N>` invocations.

Issue #616. Spec: issue body GT-001 / GT-002 (CLI dispatch path).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[5]


def _run_atdd(*args: str, env_overrides: dict | None = None) -> subprocess.CompletedProcess:
    import os
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "atdd"] + list(args),
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )


def test_coach_status_reachable_via_cli(tmp_path: Path):
    """`atdd coach status` dispatches without crashing (no runtime dir → exit 0)."""
    result = _run_atdd(
        "coach", "status",
        env_overrides={"ATDD_RUNTIME_DIR": str(tmp_path / ".atdd" / "runtime")},
    )
    assert result.returncode == 0, (
        f"atdd coach status failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "No coach runs found" in result.stdout


def test_coach_status_no_runs_message(tmp_path: Path):
    """No runs → message mentions 'runtime/coach'."""
    result = _run_atdd(
        "coach", "status",
        env_overrides={"ATDD_RUNTIME_DIR": str(tmp_path / ".atdd" / "runtime")},
    )
    combined = result.stdout + result.stderr
    assert "runtime/coach" in combined or "No coach runs found" in combined


def test_existing_coach_run_not_broken(tmp_path: Path):
    """`atdd coach 358 --dry-run` still initializes the state machine (backward compat)."""
    result = _run_atdd("coach", "358", "--dry-run")
    # Should exit 0 and print planned path
    assert result.returncode == 0, (
        f"atdd coach 358 --dry-run failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "358" in result.stdout
