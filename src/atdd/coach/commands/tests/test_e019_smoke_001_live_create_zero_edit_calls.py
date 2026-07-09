# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:E019-SMOKE-001-live-create-zero-edit-calls
# Acceptance: acc:govern-lifecycle:E019-SMOKE-001-live-create-zero-edit-calls
# WMBT: wmbt:govern-lifecycle:E019
# Phase: SMOKE
# Layer: backend.smoke
"""
AC-SMOKE-001: On the live #792 branch, the create_new_issue path results in zero
gh issue edit calls for body replacement. Exercised via ATDD_DRY_RUN=1 so no
real GitHub issue is filed.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__)
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _src_path() -> str:
    return str(_repo_root() / "src")


@pytest.mark.smoke
def test_dry_run_issue_create_reports_single_action(tmp_path):
    """`atdd author issue --dry-run` renders once and writes NOTHING.

    Retargeted by C5b (#1309): the acceptance's subject — a create dry-run that
    performs zero mutating GitHub calls — moved from the removed
    `atdd issue <slug> --dry-run` onto the canonical `atdd author issue`. The
    zero-write guarantee is now checked directly (no State Store is created
    under a temp control root) rather than inferred from output prose.
    """
    root = _repo_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = _src_path() + os.pathsep + env.get("PYTHONPATH", "")
    env["ATDD_CONTROL_ROOT"] = str(tmp_path)
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [sys.executable, "-m", "atdd", "author", "issue", "--title", "E019 dry run",
         "--slug", "smoke-test-e019-dry-run", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(root),
        env=env,
    )
    output = result.stdout + result.stderr

    assert result.returncode == 0, (
        f"`atdd author issue --dry-run` exited {result.returncode}:\n{output}"
    )
    # It rendered a body ...
    assert "## Issue Metadata" in result.stdout, (
        f"dry-run must print the rendered body on stdout:\n{output}"
    )
    # ... and performed no mutating step: no store, no gh edit/create.
    assert not (tmp_path / ".atdd" / "state" / "state.sqlite").exists(), (
        "dry-run must not create or write the State Store"
    )
    assert "issue edit" not in output.lower(), (
        f"Unexpected body-edit step in dry-run output:\n{output}"
    )


@pytest.mark.smoke
def test_dry_run_output_contains_validated_body_not_placeholder():
    """dry-run output shows the validated body, not the scaffold placeholder."""
    root = _repo_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = _src_path() + os.pathsep + env.get("PYTHONPATH", "")
    env["ATDD_DRY_RUN"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "atdd", "author", "issue", "--title", "E019 body check",
         "--slug", "smoke-test-e019-body-check", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(root),
        env=env,
    )
    output = result.stdout + result.stderr

    # Must exit 0 — dry-run is a supported flag
    assert result.returncode == 0, (
        f"`atdd author issue --dry-run` must exit 0; got {result.returncode}:\n{output}"
    )
    assert "(graph context will be injected" not in output, (
        "dry-run must NOT emit the scaffold placeholder — body should be validated/rendered"
    )
    # Positive signal: the dry-run output includes graph context content
    assert "graph context" in output.lower() or "### Graph Context" in output, (
        f"Expected rendered '### Graph Context' in dry-run output:\n{output}"
    )
