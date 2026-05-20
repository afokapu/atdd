# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:E019-UNIT-003-edit-reruns-check-gate
# Acceptance: acc:govern-lifecycle:E019-UNIT-003-edit-reruns-check-gate
# WMBT: wmbt:govern-lifecycle:E019
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-003: IssueManager.edit_issue_body() re-runs the --check gate before
sending to GitHub. A non-compliant replacement body raises IssueBodyComplianceError
with zero gh calls made.

RED state: edit_issue_body() does not yet exist on IssueManager; IssueBodyComplianceError
does not yet exist. This test must fail until GREEN.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _minimal_config(tmp_path: Path) -> None:
    atdd = tmp_path / ".atdd"
    atdd.mkdir()
    (atdd / "config.yaml").write_text(
        "github:\n  repo: test-org/test-repo\n  project_id: PVT_001\n"
    )
    (atdd / "manifest.yaml").write_text("issues: {}\nbranches: {}\n")


def _bad_body() -> str:
    return (
        "## Problem\n\nUpdated problem description.\n\n"
        "## Architecture\n\n"
        "### Mirror Across Agents\n\nAgent table.\n\n"
        # NOTE: '### Graph Context' intentionally omitted
    )


def _good_body() -> str:
    return (
        "## Problem\n\nUpdated problem description.\n\n"
        "## Architecture\n\n"
        "### Graph Context\n\nReal graph content.\n\n"
        "### Mirror Across Agents\n\nAgent table.\n\n"
        "## Acceptance\n\n- Criterion.\n"
    )


def test_edit_issue_body_refuses_non_compliant_body(tmp_path):
    """edit_issue_body raises IssueBodyComplianceError when replacement body is non-compliant."""
    _minimal_config(tmp_path)

    from atdd.coach.commands.issue import IssueBodyComplianceError, IssueManager

    gh_calls: list[list[str]] = []

    class _StubClient:
        repo = "test-org/test-repo"

        def edit_issue(self, issue_number: int, body: str) -> None:
            gh_calls.append(["issue", "edit", str(issue_number)])

    manager = IssueManager(target_dir=tmp_path)

    with patch("atdd.coach.github.GitHubClient", return_value=_StubClient()):
        with pytest.raises(IssueBodyComplianceError):
            manager.edit_issue_body(issue_number=42, body=_bad_body())

    assert len(gh_calls) == 0, (
        f"Expected 0 GitHub calls for non-compliant edit; got {gh_calls}"
    )


def test_edit_issue_body_names_failing_section_in_error(tmp_path):
    """The compliance error raised by edit_issue_body names the missing section."""
    _minimal_config(tmp_path)

    from atdd.coach.commands.issue import IssueBodyComplianceError, IssueManager

    manager = IssueManager(target_dir=tmp_path)

    with patch("atdd.coach.github.GitHubClient", return_value=MagicMock()):
        with pytest.raises(IssueBodyComplianceError) as exc_info:
            manager.edit_issue_body(issue_number=42, body=_bad_body())

    assert "Graph Context" in str(exc_info.value), (
        f"Error must name the missing section; got: {exc_info.value}"
    )


def test_edit_issue_body_proceeds_when_body_is_compliant(tmp_path):
    """edit_issue_body calls gh issue edit exactly once when the body passes --check."""
    _minimal_config(tmp_path)

    from atdd.coach.commands.issue import IssueManager

    edit_calls: list[tuple[int, str]] = []

    class _StubClient:
        repo = "test-org/test-repo"

        def edit_issue(self, issue_number: int, body: str) -> None:
            edit_calls.append((issue_number, body))

    manager = IssueManager(target_dir=tmp_path)

    with patch("atdd.coach.github.GitHubClient", return_value=_StubClient()):
        manager.edit_issue_body(issue_number=42, body=_good_body())

    assert len(edit_calls) == 1, (
        f"Expected exactly 1 gh issue edit call for compliant body; got {edit_calls}"
    )
    assert edit_calls[0][0] == 42
