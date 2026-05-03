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


def test_auto_phase_workflow_grants_projects_write():
    """Issue #384: `permissions:` must declare `projects: write`.

    Without this, the GHA token is denied ProjectV2 GraphQL writes with
    `Resource not accessible by integration`, and auto-phase silently fails
    after computing the transition. Regression of #382's intended fix.
    """
    perms = _job_permissions(_load_workflow())
    assert perms.get("projects") == "write", (
        "atdd-auto-phase.yml `permissions:` must declare `projects: write`. "
        f"Found permissions={perms!r}. Issue #384."
    )


def test_auto_phase_workflow_template_grants_projects_write():
    """Issue #384: the shipped template must declare `projects: write`.

    Catches regressions where the template ships without ProjectV2 write
    access; consumer repos receiving the template via `atdd init` would
    otherwise inherit the broken permissions block on every refresh.
    """
    perms = _job_permissions(_load_template())
    assert perms.get("projects") == "write", (
        "src/atdd/coach/templates/workflows/atdd-auto-phase.yml "
        "`permissions:` must declare `projects: write`. "
        f"Found permissions={perms!r}. Issue #384."
    )
