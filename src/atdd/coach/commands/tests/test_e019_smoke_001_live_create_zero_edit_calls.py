# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:E019-SMOKE-001-live-create-zero-edit-calls
# Acceptance: acc:govern-lifecycle:E019-SMOKE-001-live-create-zero-edit-calls
# WMBT: wmbt:govern-lifecycle:E019
# Phase: SMOKE
# Layer: backend.smoke
"""
AC-SMOKE-001: On the live #792 branch, the create_new_issue path results in zero
gh issue edit calls for body replacement. Exercised via ATDD_DRY_RUN=1 so no
real GitHub issue is filed.

RED state: IssueBodyChecker and create_new_issue (with dry-run + compliance gate)
do not yet exist. This test must fail until GREEN.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__)
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _src_path() -> str:
    return str(_repo_root() / "src")


def test_dry_run_issue_create_reports_single_action():
    """atdd issue <slug> --dry-run reports a single create action with no body-edit step."""
    root = _repo_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = _src_path() + os.pathsep + env.get("PYTHONPATH", "")
    env["ATDD_DRY_RUN"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "atdd", "issue", "smoke-test-e019-dry-run", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(root),
        env=env,
    )
    output = result.stdout + result.stderr

    assert result.returncode == 0, (
        f"atdd issue --dry-run exited {result.returncode}:\n{output}"
    )
    assert "issue edit" not in output.lower() or "body" not in output.lower(), (
        f"Unexpected body-edit step in dry-run output:\n{output}"
    )
    assert "issue create" in output.lower() or "dry" in output.lower() or "would create" in output.lower(), (
        f"Expected create action notice in dry-run output:\n{output}"
    )


def test_dry_run_output_contains_validated_body_not_placeholder():
    """dry-run output shows the validated body, not the scaffold placeholder."""
    root = _repo_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = _src_path() + os.pathsep + env.get("PYTHONPATH", "")
    env["ATDD_DRY_RUN"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "atdd", "issue", "smoke-test-e019-body-check", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(root),
        env=env,
    )
    output = result.stdout + result.stderr

    # Must exit 0 — dry-run is a supported flag
    assert result.returncode == 0, (
        f"atdd issue --dry-run must exit 0; got {result.returncode}:\n{output}"
    )
    assert "(graph context will be injected" not in output, (
        "dry-run must NOT emit the scaffold placeholder — body should be validated/rendered"
    )
    # Positive signal: the dry-run output includes graph context content
    assert "graph context" in output.lower() or "### Graph Context" in output, (
        f"Expected rendered '### Graph Context' in dry-run output:\n{output}"
    )
