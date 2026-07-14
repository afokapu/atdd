"""
Coach validator: assert the atdd-auto-phase GitHub Actions workflow exists.

Issue #355: PR-merge → phase advance is enforced by
.github/workflows/atdd-auto-phase.yml. If the file is removed or stops
dispatching `atdd auto-phase`, hand-typed transitions creep back in. This
validator hard-fails CI when the workflow file regresses.

Run: atdd validate coach
"""

from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root

# Toolkit dogfood: asserts on toolkit-only repo content (#1475).
pytestmark = [pytest.mark.platform]

REPO_ROOT = find_repo_root()
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "atdd-auto-phase.yml"
TEMPLATE_PATH = (
    REPO_ROOT
    / "src" / "atdd" / "coach" / "templates" / "workflows" / "atdd-auto-phase.yml"
)


def _load_workflow() -> dict:
    if not WORKFLOW_PATH.exists():
        pytest.fail(
            f"Missing workflow file: {WORKFLOW_PATH.relative_to(REPO_ROOT)}. "
            "Issue #355 requires this workflow to auto-transition issue "
            "phase on PR merge."
        )
    return yaml.safe_load(WORKFLOW_PATH.read_text()) or {}


def _load_template() -> dict:
    if not TEMPLATE_PATH.exists():
        pytest.skip(
            f"Template not present at {TEMPLATE_PATH.relative_to(REPO_ROOT)} "
            "(consumer repo without toolkit source) — deployed-file checks "
            "still apply."
        )
    return yaml.safe_load(TEMPLATE_PATH.read_text()) or {}


def _job_permissions(wf: dict) -> dict:
    """Extract the auto-phase job's `permissions:` block."""
    return ((wf.get("jobs") or {}).get("auto-phase") or {}).get("permissions") or {}


def test_auto_phase_workflow_file_exists():
    """File must exist at the canonical path."""
    assert WORKFLOW_PATH.exists(), (
        f"{WORKFLOW_PATH.relative_to(REPO_ROOT)} is required (issue #355)."
    )


def test_auto_phase_workflow_triggers_on_pr_close():
    """Must fire on `pull_request: closed`."""
    wf = _load_workflow()
    # PyYAML parses the bare key `on` as Python True; tolerate both.
    triggers = wf.get("on") or wf.get(True) or {}
    pr_trigger = triggers.get("pull_request") or {}
    types = pr_trigger.get("types") or []
    assert "closed" in types, (
        "atdd-auto-phase.yml must trigger on pull_request: closed; "
        f"found types={types!r}"
    )


def test_auto_phase_workflow_gated_on_merged():
    """Must guard with `merged == true` so unmerged closes don't transition."""
    content = WORKFLOW_PATH.read_text()
    assert "merged == true" in content, (
        "atdd-auto-phase.yml must gate the job on "
        "`github.event.pull_request.merged == true`."
    )


def test_auto_phase_workflow_invokes_atdd_auto_phase():
    """Must dispatch to `atdd auto-phase` so the state-machine logic runs."""
    content = WORKFLOW_PATH.read_text()
    assert "auto-phase" in content, (
        "atdd-auto-phase.yml must invoke `atdd auto-phase` (or "
        "`python -m atdd.cli auto-phase`) to perform the transition."
    )


_PROJECT_TOKEN_FALLBACK_EXPR = (
    "${{ secrets.PROJECT_TOKEN || secrets.GITHUB_TOKEN }}"
)


def _job_env(wf: dict) -> dict:
    """Extract the `env:` block from the auto-phase job's `Run atdd auto-phase` step."""
    job = (wf.get("jobs") or {}).get("auto-phase") or {}
    for step in job.get("steps") or []:
        if "auto-phase" in (step.get("name") or "").lower():
            return step.get("env") or {}
    return {}


def test_auto_phase_workflow_does_not_request_projects_write():
    """Issue #404: `permissions:` must NOT declare `projects: write`.

    GITHUB_TOKEN cannot grant the account-level Projects scope, so declaring
    `projects: write` caused GitHub to reject the workflow at preflight on
    every run (0-second 'workflow file issue' failure). The fix dropped the
    permission and moved full ProjectV2 sync to an opt-in PROJECT_TOKEN PAT;
    the GH_TOKEN fallback expression silently degrades to label-only sync
    when no PAT is present.
    """
    perms = _job_permissions(_load_workflow())
    assert "projects" not in perms, (
        "atdd-auto-phase.yml `permissions:` MUST NOT declare any `projects:` "
        "scope — GITHUB_TOKEN cannot satisfy it and preflight rejects the "
        f"workflow. Found permissions={perms!r}. Issue #404."
    )


def test_auto_phase_workflow_template_does_not_request_projects_write():
    """Issue #404: the shipped template must not declare `projects: write` either.

    Otherwise `atdd init --force` would regress every consumer repo back to
    the broken preflight shape.
    """
    perms = _job_permissions(_load_template())
    assert "projects" not in perms, (
        "src/atdd/coach/templates/workflows/atdd-auto-phase.yml "
        "`permissions:` MUST NOT declare any `projects:` scope. "
        f"Found permissions={perms!r}. Issue #404."
    )


def test_auto_phase_workflow_uses_project_token_fallback():
    """Issue #404: `GH_TOKEN` must use the PROJECT_TOKEN || GITHUB_TOKEN fallback.

    The fallback supports both modes without per-consumer setup:
      * with PROJECT_TOKEN set → full ProjectV2 Status-field sync.
      * without PROJECT_TOKEN  → GITHUB_TOKEN fallback, label-only sync via
        `IssueManager.update`'s access-denial path.
    A hard-coded `${{ secrets.GITHUB_TOKEN }}` would lock out optional PAT
    consumers; a hard-coded `${{ secrets.PROJECT_TOKEN }}` would break every
    default consumer that hasn't created the PAT.
    """
    env = _job_env(_load_workflow())
    gh_token = env.get("GH_TOKEN", "")
    assert gh_token == _PROJECT_TOKEN_FALLBACK_EXPR, (
        "atdd-auto-phase.yml `GH_TOKEN` must be "
        f"'{_PROJECT_TOKEN_FALLBACK_EXPR}' so a PROJECT_TOKEN PAT, when set, "
        "is preferred and GITHUB_TOKEN is the safe fallback. "
        f"Found GH_TOKEN={gh_token!r}. Issue #404."
    )


def test_auto_phase_workflow_template_uses_project_token_fallback():
    """Issue #404: the shipped template must also use the fallback expression."""
    env = _job_env(_load_template())
    gh_token = env.get("GH_TOKEN", "")
    assert gh_token == _PROJECT_TOKEN_FALLBACK_EXPR, (
        "src/atdd/coach/templates/workflows/atdd-auto-phase.yml `GH_TOKEN` "
        f"must be '{_PROJECT_TOKEN_FALLBACK_EXPR}'. "
        f"Found GH_TOKEN={gh_token!r}. Issue #404."
    )
