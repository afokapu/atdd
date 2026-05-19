# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:E019-UNIT-001-single-graphql-call-on-create
# Acceptance: acc:govern-lifecycle:E019-UNIT-001-single-graphql-call-on-create
# WMBT: wmbt:govern-lifecycle:E019
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-001: IssueManager.create_new_issue() invokes gh exactly once (issue create,
no follow-up issue edit for body replacement).

RED state: IssueBodyChecker does not yet exist; create_new_issue does not yet
call a compliance gate before publishing. This test must fail until GREEN.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def _minimal_config(tmp_path: Path) -> None:
    atdd = tmp_path / ".atdd"
    atdd.mkdir()
    (atdd / "config.yaml").write_text(
        "github:\n  repo: test-org/test-repo\n  project_id: PVT_001\n"
    )
    (atdd / "manifest.yaml").write_text("issues: {}\nbranches: {}\n")


def _compliant_body() -> str:
    return (
        "## Problem\n\nSome problem.\n\n"
        "## Proposed design\n\nSome design.\n\n"
        "## Architecture\n\n"
        "### Graph Context\n\nReal graph content here.\n\n"
        "### Mirror Across Agents\n\nAgent table here.\n\n"
        "## Acceptance\n\n- Some acceptance criterion.\n"
    )


def test_create_new_issue_calls_gh_create_exactly_once(tmp_path):
    """create_new_issue must call 'gh issue create' exactly once — no second edit call."""
    _minimal_config(tmp_path)

    from atdd.coach.commands.issue import IssueBodyChecker, IssueManager

    gh_calls: list[list[str]] = []

    class _StubClient:
        repo = "test-org/test-repo"
        project_id = None

        def create_issue(self, title: str, body: str, labels=None) -> int:
            gh_calls.append(["issue", "create"])
            return 9999

        def edit_issue_body(self, issue_number: int, body: str) -> None:
            gh_calls.append(["issue", "edit", "--body"])

        def add_issue_to_project(self, issue_number: int):
            return "item-id"

        def get_project_fields(self):
            return {}

        def set_project_field_select(self, *a, **kw):
            pass

        def set_project_field_text(self, *a, **kw):
            pass

    manager = IssueManager(target_dir=tmp_path)

    checker = IssueBodyChecker()
    compliant_body = _compliant_body()
    assert checker.check(compliant_body).passed, "fixture body must be compliant"

    with (
        patch("atdd.coach.commands.issue.GitHubClient", return_value=_StubClient()),
        patch.object(manager, "_render_parent_body", return_value=compliant_body),
        patch.object(manager, "_inject_graph_context", side_effect=lambda b, *a, **kw: b),
        patch.object(manager, "_discover_wmbts", return_value=[]),
        patch.object(manager, "_commit_manifest_change", return_value=None),
        patch.object(manager, "_register_issue_in_manifest", return_value=None),
    ):
        manager.create_new_issue(slug="test-feature")

    create_calls = [c for c in gh_calls if c[0:2] == ["issue", "create"]]
    edit_body_calls = [c for c in gh_calls if "edit" in c and "--body" in c]

    assert len(create_calls) == 1, (
        f"Expected exactly 1 'gh issue create' call; got {len(create_calls)}. "
        f"All calls: {gh_calls}"
    )
    assert len(edit_body_calls) == 0, (
        f"Expected 0 body-edit calls after create; got {len(edit_body_calls)}. "
        f"All calls: {gh_calls}"
    )


def test_create_call_carries_full_body_not_placeholder(tmp_path):
    """The single create call must carry the fully validated body, not a scaffold placeholder."""
    _minimal_config(tmp_path)

    from atdd.coach.commands.issue import IssueBodyChecker, IssueManager

    received_body: list[str] = []

    class _StubClient:
        repo = "test-org/test-repo"
        project_id = None

        def create_issue(self, title: str, body: str, labels=None) -> int:
            received_body.append(body)
            return 9999

        def add_issue_to_project(self, *a, **kw):
            return "item-id"

        def get_project_fields(self):
            return {}

        def set_project_field_select(self, *a, **kw):
            pass

        def set_project_field_text(self, *a, **kw):
            pass

    compliant_body = _compliant_body()
    manager = IssueManager(target_dir=tmp_path)

    with (
        patch("atdd.coach.github.GitHubClient", return_value=_StubClient()),
        patch.object(manager, "_render_parent_body", return_value=compliant_body),
        patch.object(manager, "_inject_graph_context", side_effect=lambda b, *a, **kw: b),
        patch.object(manager, "_discover_wmbts", return_value=[]),
        patch.object(manager, "_commit_manifest_change", return_value=None),
        patch.object(manager, "_register_issue_in_manifest", return_value=None),
    ):
        manager.create_new_issue(slug="test-feature")

    assert len(received_body) == 1, f"Expected body captured once; got {len(received_body)}"
    assert "Graph Context" in received_body[0], (
        "The body sent to GitHub must contain '### Graph Context'"
    )
    assert "(graph context will be injected" not in received_body[0], (
        "The body must NOT contain the scaffold placeholder"
    )
