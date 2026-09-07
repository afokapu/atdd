# URN: test:govern-lifecycle:pr-base-guard-stack-awareness:C018-UNIT-001-a-base-that-is-an-open-pr-head-is-not-a-violation
# Acceptance: acc:govern-lifecycle:C018-UNIT-001-a-base-that-is-an-open-pr-head-is-not-a-violation
# WMBT: wmbt:govern-lifecycle:C018
# Phase: RED
# Layer: application
"""C018-UNIT-001 — a tracked stack is exempt; a phantom base still violates.

The guard exists (#477/#475) because a PR based on a sibling branch orphans onto
a phantom ref once that branch is deleted. A base that is the head of another
OPEN pull request is not that case: it is tracked, its deletion is not silent,
and GitHub retargets the stack when the base PR merges.

The distinction must hold in both directions, which is why the negative cases
carry as much weight here as the exemption.
"""
from __future__ import annotations

from atdd.coach.validators.test_pr_base_branch import evaluate_base_violations


def test_a_stacked_pr_is_not_a_violation():
    # #1799 stacked on #1796 — the shape that red-lighted the whole queue.
    open_prs = [
        {"number": 1796, "baseRefName": "main",
         "headRefName": "feat/documentation-obligation-core"},
        {"number": 1799, "baseRefName": "feat/documentation-obligation-core",
         "headRefName": "feat/documentation-declaration-integrity"},
    ]
    violations = evaluate_base_violations(open_prs, default_branch="main")

    assert violations == [], (
        "a base that is another OPEN PR's head is tracked, not phantom, so it "
        f"must not violate; got {[v.location for v in violations]}"
    )


def test_a_base_belonging_to_no_open_pr_still_violates():
    # The guard #477 added must be narrowed, never weakened.
    open_prs = [
        {"number": 10, "baseRefName": "main", "headRefName": "feat/x"},
        {"number": 11, "baseRefName": "fix/deleted-sibling", "headRefName": "feat/y"},
    ]
    violations = evaluate_base_violations(open_prs, default_branch="main")

    assert [v.location for v in violations] == ["PR#11"], (
        "a base no open PR is producing is exactly the orphan risk this guard "
        f"exists for; got {[v.location for v in violations]}"
    )


def test_a_stack_does_not_excuse_an_unrelated_orphan():
    """One tracked stack must not silence a genuine violation beside it."""
    open_prs = [
        {"number": 20, "baseRefName": "main", "headRefName": "feat/base"},
        {"number": 21, "baseRefName": "feat/base", "headRefName": "feat/stacked"},
        {"number": 22, "baseRefName": "release/v3", "headRefName": "feat/orphan"},
    ]
    violations = evaluate_base_violations(open_prs, default_branch="main")

    assert [v.location for v in violations] == ["PR#22"]
