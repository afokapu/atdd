# URN: test:govern-lifecycle:close-substrate-friction-regressions:E024-UNIT-002-publish-condition-includes-head-branch-main
# Acceptance: acc:govern-lifecycle:E024-UNIT-002-publish-condition-includes-head-branch-main
# WMBT: wmbt:govern-lifecycle:E024
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-002: .github/workflows/publish.yml tag-release job if-condition explicitly
requires github.event.workflow_run.head_branch == 'main'.

RED state: publish.yml currently checks only:
  github.event.workflow_run.conclusion == 'success' &&
  github.event.workflow_run.event == 'push'
It does NOT check head_branch. This test fails until head_branch == 'main' is added.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

REPO_ROOT = Path(__file__).resolve().parents[6]
PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish.yml"


def test_publish_condition_includes_head_branch_main():
    """AC-UNIT-002: publish.yml must require head_branch == 'main' in the if condition."""
    workflow_text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    assert "head_branch == 'main'" in workflow_text, (
        f"{PUBLISH_WORKFLOW} tag-release job does not require head_branch == 'main'.\n"
        "Without this guard, any push-to-any-branch ATDD Validate success can trigger\n"
        "Publish. Add: github.event.workflow_run.head_branch == 'main'\n"
        "to the tag-release if: condition (issue #845 Item C)."
    )


def test_publish_condition_retains_push_event_check():
    """AC-UNIT-002: adding head_branch must not remove the event == 'push' check."""
    workflow_text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    assert "event == 'push'" in workflow_text or "event == \"push\"" in workflow_text, (
        f"{PUBLISH_WORKFLOW} is missing event == 'push' guard — do not remove it."
    )


def test_publish_condition_retains_conclusion_success_check():
    """AC-UNIT-002: adding head_branch must not remove the conclusion == 'success' check."""
    workflow_text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    assert "conclusion == 'success'" in workflow_text or "conclusion == \"success\"" in workflow_text, (
        f"{PUBLISH_WORKFLOW} is missing conclusion == 'success' guard — do not remove it."
    )
