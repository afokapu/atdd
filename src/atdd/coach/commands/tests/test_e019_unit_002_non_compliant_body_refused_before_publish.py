# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:E019-UNIT-002-non-compliant-body-refused-before-publish
# Acceptance: acc:govern-lifecycle:E019-UNIT-002-non-compliant-body-refused-before-publish
# WMBT: wmbt:govern-lifecycle:E019
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-002: When the local body template fails --check, create_new_issue raises
IssueBodyComplianceError and makes zero GitHub calls.

RED state: IssueBodyComplianceError and IssueBodyChecker do not yet exist.
This test must fail until GREEN.
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


def _body_missing_graph_context() -> str:
    return (
        "## Problem\n\nSome problem.\n\n"
        "## Proposed design\n\nSome design.\n\n"
        "## Architecture\n\n"
        "### Mirror Across Agents\n\nAgent table here.\n\n"
        "## Acceptance\n\n- Some acceptance criterion.\n"
        # NOTE: '### Graph Context' section intentionally omitted
    )


def _body_missing_mirror_across_agents() -> str:
    return (
        "## Problem\n\nSome problem.\n\n"
        "## Architecture\n\n"
        "### Graph Context\n\nReal graph content here.\n\n"
        "## Acceptance\n\n- Some acceptance criterion.\n"
        # NOTE: '### Mirror Across Agents' section intentionally omitted
    )


def test_non_compliant_body_raises_compliance_error(tmp_path):
    """create_new_issue refuses to publish when the body is missing ### Graph Context."""
    _minimal_config(tmp_path)

    from atdd.coach.commands.issue import IssueBodyComplianceError, IssueManager

    gh_calls: list[list[str]] = []

    class _StubClient:
        repo = "test-org/test-repo"

        def create_issue(self, title: str, body: str, labels=None) -> int:
            gh_calls.append(["issue", "create"])
            return 9999

    bad_body = _body_missing_graph_context()
    manager = IssueManager(target_dir=tmp_path)

    with (
        patch("atdd.coach.github.GitHubClient", return_value=_StubClient()),
        patch.object(manager, "_render_parent_body", return_value=bad_body),
        patch.object(manager, "_inject_graph_context", side_effect=lambda b, *a, **kw: b),
        patch.object(manager, "_discover_wmbts", return_value=[]),
    ):
        with pytest.raises(IssueBodyComplianceError):
            manager.create_new_issue(slug="bad-feature")

    assert len(gh_calls) == 0, (
        f"Expected 0 GitHub calls when body is non-compliant; got {gh_calls}"
    )


def test_non_compliant_body_error_names_missing_section(tmp_path):
    """The IssueBodyComplianceError message names the failing section."""
    _minimal_config(tmp_path)

    from atdd.coach.commands.issue import IssueBodyComplianceError, IssueManager

    bad_body = _body_missing_graph_context()
    manager = IssueManager(target_dir=tmp_path)

    with (
        patch("atdd.coach.github.GitHubClient", return_value=MagicMock()),
        patch.object(manager, "_render_parent_body", return_value=bad_body),
        patch.object(manager, "_inject_graph_context", side_effect=lambda b, *a, **kw: b),
        patch.object(manager, "_discover_wmbts", return_value=[]),
    ):
        with pytest.raises(IssueBodyComplianceError) as exc_info:
            manager.create_new_issue(slug="bad-feature")

    assert "Graph Context" in str(exc_info.value), (
        f"Expected 'Graph Context' in error; got: {exc_info.value}"
    )


def test_missing_mirror_across_agents_also_refused(tmp_path):
    """create_new_issue also refuses when ### Mirror Across Agents is missing."""
    _minimal_config(tmp_path)

    from atdd.coach.commands.issue import IssueBodyComplianceError, IssueManager

    gh_calls: list[list[str]] = []

    class _StubClient:
        repo = "test-org/test-repo"

        def create_issue(self, title: str, body: str, labels=None) -> int:
            gh_calls.append(["issue", "create"])
            return 9999

    bad_body = _body_missing_mirror_across_agents()
    manager = IssueManager(target_dir=tmp_path)

    with (
        patch("atdd.coach.github.GitHubClient", return_value=_StubClient()),
        patch.object(manager, "_render_parent_body", return_value=bad_body),
        patch.object(manager, "_inject_graph_context", side_effect=lambda b, *a, **kw: b),
        patch.object(manager, "_discover_wmbts", return_value=[]),
    ):
        with pytest.raises(IssueBodyComplianceError):
            manager.create_new_issue(slug="bad-feature-no-mirror")

    assert len(gh_calls) == 0, (
        f"Expected 0 GitHub calls when body is non-compliant; got {gh_calls}"
    )
