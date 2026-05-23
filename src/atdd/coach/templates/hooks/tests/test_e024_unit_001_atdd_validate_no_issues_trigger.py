# URN: test:govern-lifecycle:close-substrate-friction-regressions:E024-UNIT-001-atdd-validate-has-no-issues-trigger
# Acceptance: acc:govern-lifecycle:E024-UNIT-001-atdd-validate-has-no-issues-trigger
# WMBT: wmbt:govern-lifecycle:E024
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-001: .github/workflows/atdd-validate.yml does not contain an 'issues' event trigger.

RED state: atdd-validate.yml currently lists 'issues' in its 'on:' block (types:
opened, edited, closed, labeled, unlabeled). Each issues-triggered run spawns a
Publish workflow_run skip, creating noisy false-negative UX for operators. This
test fails until the issues trigger is removed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

REPO_ROOT = Path(__file__).resolve().parents[6]
VALIDATE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "atdd-validate.yml"


def test_atdd_validate_has_no_issues_trigger():
    """AC-UNIT-001: atdd-validate.yml must not contain an 'issues' event trigger."""
    workflow_text = VALIDATE_WORKFLOW.read_text(encoding="utf-8")
    assert "issues:" not in workflow_text, (
        f"{VALIDATE_WORKFLOW} still contains an 'issues:' trigger.\n"
        "Each issues-triggered ATDD Validate run fires the Publish workflow_run event,\n"
        "which then appears as 'skipped' in GitHub Actions — creating the false impression\n"
        "that auto-publish is broken (issue #845 Item C).\n"
        "Remove the 'issues:' block from the 'on:' section."
    )


def test_atdd_validate_retains_push_and_pull_request_triggers():
    """AC-UNIT-001: removing issues trigger must not remove push or pull_request triggers."""
    workflow_text = VALIDATE_WORKFLOW.read_text(encoding="utf-8")
    assert "push:" in workflow_text, (
        f"{VALIDATE_WORKFLOW} is missing the 'push:' trigger — do not remove it."
    )
    assert "pull_request:" in workflow_text, (
        f"{VALIDATE_WORKFLOW} is missing the 'pull_request:' trigger — do not remove it."
    )
