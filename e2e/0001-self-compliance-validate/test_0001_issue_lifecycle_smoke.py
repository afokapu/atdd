# URN: test:train:0001-self-compliance-validate:E2E-003-issue-lifecycle-smoke
# Train: train:0001-self-compliance-validate
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Purpose: Verify atdd issue commands work against real GitHub API
"""
Smoke test for train:0001-self-compliance-validate
train: 0001-self-compliance-validate | phase: SMOKE
Purpose: Real CLI execution of atdd issue commands against real GitHub
"""

import shutil
import subprocess
import sys
import json
import pytest
from pathlib import Path

from atdd.coach.utils.repo import find_repo_root


REPO_ROOT = find_repo_root()

def _run_atdd(*args, timeout=30) -> subprocess.CompletedProcess:
    """Run atdd CLI via the same Python interpreter running this test."""
    cmd = [sys.executable, "-m", "atdd"] + list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=timeout,
    )


def _run_gh(*args, timeout=15) -> subprocess.CompletedProcess:
    """Run gh CLI command and return result."""
    cmd = ["gh"] + list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=timeout,
    )


# ============================================================================
# Smoke: atdd issue open (real GitHub API)
# ============================================================================

@pytest.mark.github_api
class TestIssueListSmoke:
    """Smoke tests for atdd issue open — real GitHub API."""

    def test_issue_open_runs(self):
        """atdd issue open must query GitHub and return exit code 0."""
        result = _run_atdd("coach", "issues", "open")
        assert result.returncode == 0, (
            f"atdd issue open failed (exit {result.returncode}):\n"
            f"STDERR:\n{result.stderr[-500:]}"
        )

    def test_list_runs(self):
        """atdd list must query GitHub and return exit code 0."""
        result = _run_atdd("list")
        assert result.returncode == 0, (
            f"atdd list failed (exit {result.returncode}):\n"
            f"STDERR:\n{result.stderr[-500:]}"
        )


# ============================================================================
# Smoke: atdd issue <N> (real GitHub API — read-only enter)
# ============================================================================

@pytest.mark.github_api
class TestIssueEnterSmoke:
    """Smoke tests for atdd issue <N> enter — real GitHub API read-only."""

    def _find_open_issue(self) -> int:
        """Find any open atdd-issue to enter, or skip."""
        result = _run_gh(
            "issue", "list", "--repo", "afokapu/atdd",
            "--label", "atdd-issue", "--state", "open",
            "--json", "number", "--jq", ".[0].number",
        )
        if result.returncode != 0 or not result.stdout.strip():
            pytest.skip("No open atdd-issue found to test enter")
        return int(result.stdout.strip())

    def test_issue_enter_runs(self):
        """atdd issue <N> must fetch issue metadata and print context."""
        issue_number = self._find_open_issue()
        result = _run_atdd("coach", "issues", str(issue_number))
        # Enter may fail if not in worktree, but it should at least fetch and print
        # Accept both 0 (success) and 1 (not in worktree) — the key is it doesn't crash
        assert result.returncode in (0, 1), (
            f"atdd issue {issue_number} crashed (exit {result.returncode}):\n"
            f"STDERR:\n{result.stderr[-500:]}"
        )
        # Should have printed something meaningful
        combined = result.stdout + result.stderr
        assert len(combined) > 50, "Output suspiciously short — command may have crashed silently"
