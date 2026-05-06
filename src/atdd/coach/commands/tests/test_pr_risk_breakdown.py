# URN: component:govern-lifecycle:enforcement-substrate:pr_risk_breakdown:backend:tests
# Runtime: python
# Purpose: Cover risk-score breakdown emission inside the PR body (issue #418, AC #2).

"""
Integration tests for ``PRManager._build_pr_body`` risk-score breakdown.

Substrate spec v12 §8.3 + issue #418 AC #2 require that the PR description
emitted by ``atdd pr`` includes a "## Risk score breakdown" section. These
tests exercise ``_build_pr_body`` directly with a stubbed Violation list to
keep the GitHub side-effects (``gh pr create``) out of scope.
"""

from __future__ import annotations

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.utils.risk_score import ARCHETYPES
from atdd.coach.validators._violation import Violation


pytestmark = [pytest.mark.platform]


def _v(rule_id: str, severity: int) -> Violation:
    return Violation(
        rule_id=rule_id,
        severity=severity,
        location="x.py:1",
        detail="fixture",
    )


def test_pr_body_includes_risk_breakdown_section():
    """AC #2 of issue #418: the PR body emits a "## Risk score breakdown"
    section showing per-archetype severity sums."""
    manager = PRManager()
    body = manager._build_pr_body(
        issue_number=418,
        issue_data={"labels": []},
        sub_issues=[],
        manifest_entry=None,
        violations=[
            _v("coder.green.x", 3),
            _v("repo.acceptance.foo", 4),
            _v("repo.security.session", 5),
        ],
    )

    assert "## Risk score breakdown" in body
    for arch in ARCHETYPES:
        assert f"| {arch} |" in body
    # Slice values: coder=3, repo=9, others=0
    assert "| coder | 3 |" in body
    assert "| repo | 9 |" in body
    assert "| coach | 0 |" in body
    assert "**total**" in body
    assert "**12**" in body


def test_pr_body_renders_zero_breakdown_when_no_violations():
    """The substrate is present even with no debt — every archetype slice is
    rendered as 0 so reviewers see the breakdown is "clean", not absent."""
    manager = PRManager()
    body = manager._build_pr_body(
        issue_number=418,
        issue_data={"labels": []},
        sub_issues=[],
        manifest_entry=None,
        violations=[],
    )

    assert "## Risk score breakdown" in body
    for arch in ARCHETYPES:
        assert f"| {arch} | 0 |" in body
    assert "**0**" in body


def test_pr_body_breakdown_appears_before_footer():
    """The breakdown belongs above the trailing "PR created by" footer so it
    reads alongside other content sections rather than below the divider."""
    manager = PRManager()
    body = manager._build_pr_body(
        issue_number=418,
        issue_data={"labels": []},
        sub_issues=[],
        manifest_entry=None,
        violations=[_v("coder.green.x", 1)],
    )

    breakdown_idx = body.index("## Risk score breakdown")
    footer_idx = body.index("PR created by `atdd pr`.")
    assert breakdown_idx < footer_idx


def test_pr_body_uses_collect_violations_when_argument_omitted(monkeypatch):
    """When no Violation list is passed, the manager falls back to
    ``_collect_violations``. This is the substrate hook a future aggregator
    will override (see issue #418 prerequisite acknowledgement)."""
    manager = PRManager()
    monkeypatch.setattr(
        manager,
        "_collect_violations",
        lambda: [_v("planner.criteria.shape", 4)],
    )
    body = manager._build_pr_body(
        issue_number=418,
        issue_data={"labels": []},
        sub_issues=[],
        manifest_entry=None,
    )

    assert "| planner | 4 |" in body
    assert "**4**" in body
