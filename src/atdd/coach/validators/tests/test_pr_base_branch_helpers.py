"""
Pure-evaluator unit tests for the PR base-branch validator (issue #477).

Co-located with the other validator helper tests under
``src/atdd/coach/validators/tests/``. These tests exercise
``evaluate_base_violations`` directly with synthetic ``gh pr list``
payloads — no network, no marker, no disposition-gate.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators._violation import Violation
from atdd.coach.validators.test_pr_base_branch import (
    _RULE,
    evaluate_base_violations,
)


def test_evaluate_returns_empty_when_every_pr_targets_default():
    """No Violations when every open PR's baseRefName == default branch."""
    open_prs = [
        {"number": 1, "baseRefName": "main", "headRefName": "feat/a"},
        {"number": 2, "baseRefName": "main", "headRefName": "fix/b"},
    ]
    violations = evaluate_base_violations(open_prs, default_branch="main")
    assert violations == []


def test_evaluate_emits_structured_violation_for_non_default_base():
    """A non-default baseRefName produces one Violation with rule_id bound."""
    open_prs = [
        {
            "number": 475,
            "baseRefName": "fix/473-init-template-fix",
            "headRefName": "feat/473-phase-2-3",
        },
    ]
    violations = evaluate_base_violations(open_prs, default_branch="main")

    assert len(violations) == 1
    v = violations[0]
    assert isinstance(v, Violation)
    assert v.rule_id == _RULE.rule_id == "coach.pr.base-must-be-default-branch"
    assert v.severity == _RULE.severity
    assert "475" in v.location
    assert "fix/473-init-template-fix" in v.detail
    assert "main" in v.detail
    assert "#477" in v.detail


def test_evaluate_emits_one_violation_per_offending_pr():
    """Multiple mistargeted PRs each produce their own Violation."""
    open_prs = [
        {"number": 10, "baseRefName": "main", "headRefName": "feat/x"},
        {"number": 11, "baseRefName": "develop", "headRefName": "feat/y"},
        {"number": 12, "baseRefName": "release/v3", "headRefName": "feat/z"},
    ]
    violations = evaluate_base_violations(open_prs, default_branch="main")

    assert len(violations) == 2
    locations = {v.location for v in violations}
    assert "PR#11" in locations
    assert "PR#12" in locations


def test_evaluate_skips_records_missing_required_fields():
    """Defensive: malformed gh-pr-list rows don't blow up the scanner."""
    open_prs = [
        {"number": None, "baseRefName": "feat/x"},
        {"baseRefName": "feat/x"},
        {"number": 99},
    ]
    violations = evaluate_base_violations(open_prs, default_branch="main")
    assert violations == []


def test_evaluate_respects_arbitrary_default_branch_name():
    """Helper is name-agnostic — works for `master`, `trunk`, etc."""
    open_prs = [
        {"number": 1, "baseRefName": "master", "headRefName": "feat/a"},
        {"number": 2, "baseRefName": "main", "headRefName": "feat/b"},
    ]
    violations = evaluate_base_violations(open_prs, default_branch="master")
    assert len(violations) == 1
    assert violations[0].location == "PR#2"
