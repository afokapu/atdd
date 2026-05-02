# URN: test:train:0001-self-compliance-validate:E2E-002-validate-lifecycle-smoke
# Train: train:0001-self-compliance-validate
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: Verify atdd validate runs against real filesystem and produces real output
"""
Smoke test for train:0001-self-compliance-validate
train: 0001-self-compliance-validate | phase: SMOKE
Purpose: Real CLI execution of atdd validate against the toolkit's own repo
"""

import shutil
import subprocess
import sys
from pathlib import Path

from atdd.coach.utils.repo import find_repo_root


REPO_ROOT = find_repo_root()

def _run_atdd(*args, timeout=60) -> subprocess.CompletedProcess:
    """Run atdd CLI via the same Python interpreter running this test."""
    cmd = [sys.executable, "-m", "atdd"] + list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=timeout,
    )


# ============================================================================
# Smoke: atdd validate (real CLI, real filesystem)
# ============================================================================

class TestValidateSmoke:
    """Smoke tests for atdd validate — real CLI against real repo."""

    def test_validate_planner_runs(self):
        """atdd validate planner --local must execute and return exit code 0."""
        result = _run_atdd("validate", "planner", "--local", "--no-split")
        assert result.returncode == 0, (
            f"atdd validate planner failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout[-500:]}\n"
            f"STDERR:\n{result.stderr[-500:]}"
        )

    def test_validate_tester_runs(self):
        """atdd validate tester --local must execute and return exit code 0."""
        result = _run_atdd("validate", "tester", "--local", "--no-split")
        assert result.returncode == 0, (
            f"atdd validate tester failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout[-500:]}\n"
            f"STDERR:\n{result.stderr[-500:]}"
        )

    def test_validate_coder_runs(self):
        """atdd validate coder --local must execute without crashing.

        Note: Some coder validators check consumer-repo-specific artifacts
        (e.g., python/trains/, e2e/conftest.py with TrainRunner) that don't
        exist in the toolkit. Test failures from missing consumer artifacts
        are expected — we only check the validator framework doesn't crash.
        """
        result = _run_atdd("validate", "coder", "--local", "--no-split")
        # Exit code 0 (all pass) or 1 (some fail) are both acceptable —
        # the key is it ran to completion (didn't crash with exit 2+)
        assert result.returncode in (0, 1), (
            f"atdd validate coder crashed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout[-500:]}\n"
            f"STDERR:\n{result.stderr[-500:]}"
        )
        # Verify it actually ran tests (not zero collected)
        assert "passed" in result.stdout or "failed" in result.stdout, (
            "Validator produced no test results — may have crashed during collection"
        )

    def test_validate_coach_runs(self):
        """atdd validate coach --local must execute and return exit code 0."""
        result = _run_atdd("validate", "coach", "--local", "--no-split")
        assert result.returncode == 0, (
            f"atdd validate coach failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout[-500:]}\n"
            f"STDERR:\n{result.stderr[-500:]}"
        )


# ============================================================================
# Smoke: atdd gate (real CLI, real filesystem)
# ============================================================================

class TestGateSmoke:
    """Smoke tests for atdd gate — real CLI against real repo."""

    def test_gate_runs(self):
        """atdd gate must execute and print loaded files."""
        result = _run_atdd("gate")
        assert result.returncode == 0, (
            f"atdd gate failed (exit {result.returncode}):\n"
            f"STDERR:\n{result.stderr[-500:]}"
        )
        assert "ATDD Gate Verification" in result.stdout
        assert "Loaded files:" in result.stdout

    def test_gate_json_runs(self):
        """atdd gate --json must produce valid JSON output."""
        import json
        result = _run_atdd("gate", "--json")
        assert result.returncode == 0, f"atdd gate --json failed: {result.stderr[-300:]}"
        data = json.loads(result.stdout)
        assert "files" in data or "loaded_files" in data or isinstance(data, dict)


# ============================================================================
# Smoke: atdd inventory (real CLI, real filesystem)
# ============================================================================

class TestInventorySmoke:
    """Smoke tests for atdd inventory — real CLI against real repo."""

    def test_inventory_runs(self):
        """atdd inventory must execute and produce YAML output."""
        result = _run_atdd("inventory")
        assert result.returncode == 0, (
            f"atdd inventory failed (exit {result.returncode}):\n"
            f"STDERR:\n{result.stderr[-500:]}"
        )
        assert len(result.stdout) > 100, "Inventory output suspiciously short"


# ============================================================================
# Smoke: atdd status (real CLI, real filesystem)
# ============================================================================

class TestStatusSmoke:
    """Smoke tests for atdd status — real CLI against real repo."""

    def test_status_runs(self):
        """atdd status must execute without error."""
        result = _run_atdd("status")
        assert result.returncode == 0, (
            f"atdd status failed (exit {result.returncode}):\n"
            f"STDERR:\n{result.stderr[-500:]}"
        )
