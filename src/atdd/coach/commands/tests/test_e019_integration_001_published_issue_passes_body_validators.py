# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:E019-INTEGRATION-001-published-issue-passes-body-validators
# Acceptance: acc:govern-lifecycle:E019-INTEGRATION-001-published-issue-passes-body-validators
# WMBT: wmbt:govern-lifecycle:E019
# Phase: SMOKE
# Layer: backend.integration
"""
AC-INTEGRATION-001: A body produced by IssueManager (via _render_parent_body + _inject_graph_context)
passes IssueBodyChecker.check() — the same rule that backs test_issue_body_has_graph_context.

RED state: IssueBodyChecker does not yet exist. This test must fail until GREEN.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture()
def repo_with_wagon(tmp_path: Path) -> Path:
    wagon_dir = tmp_path / "plan" / "integration_slug"
    _write(
        wagon_dir / "_integration_slug.yaml",
        "urn: wagon:integration-slug\n"
        "name: Integration Slug Wagon\n"
        "description: E019 integration fixture.\n"
        "features:\n"
        "  - urn: feature:integration-slug:e019-fixture\n",
    )
    _write(
        wagon_dir / "E001.yaml",
        "urn: wmbt:integration-slug:E001\n"
        "statement: Demonstrate body compliance.\n",
    )
    return tmp_path


def test_rendered_body_passes_issue_body_checker(repo_with_wagon: Path):
    """Body produced by IssueManager for a real slug passes IssueBodyChecker.check()."""
    from atdd.coach.commands.issue import IssueBodyChecker, IssueManager

    manager = IssueManager(target_dir=repo_with_wagon)
    body = manager._render_parent_body(
        slug="integration-slug",
        issue_type="implementation",
        today="2026-05-20",
        train_display="0001-self-compliance-validate",
        archetypes_display="be,wmbt",
    )
    body = manager._inject_graph_context(body, slug="integration-slug", train=None)

    checker = IssueBodyChecker()
    result = checker.check(body)

    assert result.passed, (
        f"IssueBodyChecker.check() failed on rendered body.\n"
        f"Errors: {result.errors}\n"
        f"Body excerpt:\n{body[:800]}"
    )


def test_checker_result_has_passed_attribute():
    """IssueBodyChecker.check() returns an object with a .passed bool attribute."""
    from atdd.coach.commands.issue import IssueBodyChecker

    checker = IssueBodyChecker()
    good_body = (
        "## Problem\n\nSome problem.\n\n"
        "## Architecture\n\n"
        "### Graph Context\n\nReal graph.\n\n"
        "### Mirror Across Agents\n\nTable.\n\n"
        "## Acceptance\n\n- Criterion.\n"
    )
    result = checker.check(good_body)

    assert hasattr(result, "passed"), "check() result must have a .passed attribute"
    assert isinstance(result.passed, bool)
    assert result.passed is True


def test_checker_result_has_errors_attribute_on_failure():
    """IssueBodyChecker.check() result carries .errors list when body is non-compliant."""
    from atdd.coach.commands.issue import IssueBodyChecker

    checker = IssueBodyChecker()
    bad_body = "## Problem\n\nNo Architecture section at all.\n"
    result = checker.check(bad_body)

    assert hasattr(result, "errors"), "check() result must have an .errors attribute"
    assert result.passed is False
    assert len(result.errors) > 0
