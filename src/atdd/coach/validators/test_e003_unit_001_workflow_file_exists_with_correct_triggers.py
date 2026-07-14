# URN: test:review-phase-boundaries:reviewer-pr-ci-gate:E003-UNIT-001-workflow-file-exists-with-correct-triggers
# Acceptance: acc:review-phase-boundaries:E003-UNIT-001-workflow-file-exists-with-correct-triggers
# WMBT: wmbt:review-phase-boundaries:E003
# Phase: RED
# Layer: backend.unit
# Assertion: structural

"""E003-UNIT-001 — .github/workflows/atdd-review.yml is committed, parses
as valid YAML, declares the correct PR triggers, and contains the required
atdd coach review + gh pr comment steps.

Phase RED: fails on a tree where the workflow has not been added.
Phase GREEN: workflow exists with correct structure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

pytestmark = [pytest.mark.coach, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]
WORKFLOW_FILE = REPO_ROOT / ".github" / "workflows" / "atdd-review.yml"

REQUIRED_PR_TYPES = {"opened", "synchronize", "reopened"}


def _load() -> Dict[str, Any]:
    assert WORKFLOW_FILE.exists(), (
        f"Missing {WORKFLOW_FILE}. "
        "Acceptance E003-UNIT-001 requires .github/workflows/atdd-review.yml to be committed."
    )
    with WORKFLOW_FILE.open() as fh:
        return yaml.safe_load(fh)


def test_workflow_file_exists() -> None:
    """.github/workflows/atdd-review.yml MUST exist in the repository."""
    assert WORKFLOW_FILE.exists(), (
        f"Missing {WORKFLOW_FILE}. "
        "Acceptance E003-UNIT-001 requires the per-PR review gate workflow."
    )


def test_workflow_triggers_on_correct_pr_types() -> None:
    """on.pull_request.types MUST contain opened, synchronize, and reopened."""
    wf = _load()
    on = wf.get("on") or wf.get(True)  # YAML parses 'on' as True in some versions
    if on is None:
        # Try string key
        on = wf.get("on")
    assert on is not None, "Workflow has no 'on' trigger key."
    pr_trigger = on.get("pull_request", {}) if isinstance(on, dict) else {}
    types = pr_trigger.get("types", [])
    declared = set(types)
    missing = REQUIRED_PR_TYPES - declared
    assert not missing, (
        f"on.pull_request.types is missing: {sorted(missing)}. "
        f"Required: {sorted(REQUIRED_PR_TYPES)}. Got: {sorted(declared)}."
    )


def test_workflow_has_atdd_coach_review_step() -> None:
    """At least one job step MUST invoke `atdd coach review` with --report-file."""
    wf = _load()
    jobs = wf.get("jobs", {})
    assert jobs, "Workflow has no jobs."
    found = False
    for job_name, job in jobs.items():
        steps = job.get("steps", [])
        for step in steps:
            run = step.get("run", "") or ""
            if "atdd coach review" in run and "--report-file" in run:
                found = True
                break
        if found:
            break
    assert found, (
        "No workflow step invokes `atdd coach review` with --report-file. "
        "Acceptance E003-UNIT-001 requires this step to capture the verdict."
    )


def test_workflow_has_gh_pr_comment_step() -> None:
    """At least one job step MUST invoke `gh pr comment` to post the verdict."""
    wf = _load()
    jobs = wf.get("jobs", {})
    found = False
    for job_name, job in jobs.items():
        steps = job.get("steps", [])
        for step in steps:
            run = step.get("run", "") or ""
            uses = step.get("uses", "") or ""
            if "gh pr comment" in run or "actions/github-script" in uses:
                found = True
                break
        if found:
            break
    assert found, (
        "No workflow step posts a PR comment (gh pr comment or actions/github-script). "
        "Acceptance E003-UNIT-001 requires a comment step for verdict visibility."
    )


def test_workflow_has_enforce_verdict_step() -> None:
    """At least one job step MUST contain verdict enforcement logic (exit 1 on fail)."""
    wf = _load()
    jobs = wf.get("jobs", {})
    found = False
    for job_name, job in jobs.items():
        steps = job.get("steps", [])
        for step in steps:
            run = step.get("run", "") or ""
            if "verdict" in run and ("exit 1" in run or "exit 0" in run):
                found = True
                break
        if found:
            break
    assert found, (
        "No workflow step contains verdict enforcement logic (exit 1 on fail). "
        "Acceptance E003-UNIT-001 requires the workflow to block on `fail` verdicts."
    )
