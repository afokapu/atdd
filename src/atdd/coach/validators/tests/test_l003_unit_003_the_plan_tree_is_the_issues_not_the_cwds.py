# URN: test:govern-lifecycle:bind-issue-feature:L003-UNIT-003-the-plan-tree-is-the-issues-not-the-cwds
# Acceptance: acc:govern-lifecycle:L003-UNIT-003-the-plan-tree-is-the-issues-not-the-cwds
# WMBT: wmbt:govern-lifecycle:L003
# Phase: GREEN
# Layer: presentation
# Runtime: python
# Assertion: behavioral
# Purpose: The WMBTs and paths a banner shows are read from the tree the issue's store binding names, not from the tree the command happens to run in, and standing in the issue's own worktree is unchanged.
"""GREEN test for L003-UNIT-003 — whose tree answered.

Reproduces the 2026-08-05 observation on `#1735` with the two real WMBT codes:
its banner listed `C021`, which exists only on a sibling branch, and omitted
`C020`, which `#1735`'s own commit created — with every path rooted in the
worktree the operator was standing in.

The fixture is two REAL git worktrees of one REAL repo, because the resolution
under test reads `git worktree list --porcelain`. Two plain directories would be
resolvable by nothing and the test would pass for the wrong reason.
"""
from __future__ import annotations

import pytest

from ._bind_issue_feature_helpers import (
    FEATURE_URN,
    ISSUE_BRANCH_WMBT,
    SIBLING_BRANCH_WMBT,
    make_two_worktree_repo,
    open_store,
    optional_attr,
    seed_issue,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

_RESOLVER_MODULE = "atdd.coach.commands.issue_feature_binding"

ISSUE = 96101
ISSUE_BRANCH = "feat/the-issues-own-branch"


def _attr(name):
    fn = optional_attr(_RESOLVER_MODULE, name)
    assert fn is not None, f"expected {_RESOLVER_MODULE}.{name}"
    return fn


@pytest.fixture()
def two_trees(tmp_path):
    """The issue's branch declares C020; the tree the operator stands in declares C021."""
    sibling, issue_tree = make_two_worktree_repo(tmp_path, issue_branch=ISSUE_BRANCH)

    write_plan_tree(issue_tree, wmbts=(ISSUE_BRANCH_WMBT,))
    write_plan_tree(sibling, wmbts=(SIBLING_BRANCH_WMBT,))

    # The store is seeded in both checkouts: a worktree gets `.atdd/` because
    # config.yaml is tracked, so each resolves its own store file. The binding
    # under test is the one recorded in whichever store answers.
    for root in (sibling, issue_tree):
        seed_issue(
            open_store(root), slug="own-branch-probe", issue_number=ISSUE,
            feature=FEATURE_URN, extra={"branch": ISSUE_BRANCH},
        )
    return sibling, issue_tree


def test_the_tree_is_located_through_the_store_binding(two_trees) -> None:
    sibling, issue_tree = two_trees

    tree = _attr("resolve_plan_tree")(ISSUE, control_root=sibling)

    assert getattr(tree, "source", None) == "binding", (
        "the plan tree was not resolved through the issue's branch binding; "
        f"source={getattr(tree, 'source', None)!r}"
    )
    assert getattr(tree, "branch", None) == ISSUE_BRANCH
    assert tree.root == issue_tree, (
        f"resolved against {tree.root}, not the issue's own worktree {issue_tree}"
    )


def test_the_wmbts_are_the_issues_and_not_the_cwds(two_trees) -> None:
    """The #1735 shape, in both directions at once."""
    sibling, _ = two_trees

    result = _attr("resolve_wmbts_for_issue")(ISSUE, control_root=sibling)
    wmbts = list(getattr(result, "wmbts", []))

    assert ISSUE_BRANCH_WMBT in wmbts, (
        f"the banner omitted {ISSUE_BRANCH_WMBT}, the obligation the issue's own "
        f"branch declares — the half of #1735 that hid an authored WMBT. Got {wmbts}"
    )
    assert SIBLING_BRANCH_WMBT not in wmbts, (
        f"the banner listed {SIBLING_BRANCH_WMBT}, which exists only in the tree "
        "the command ran from — an obligation belonging to another branch, "
        "asserted as this issue's"
    )


def test_every_rendered_path_is_openable_from_the_issues_checkout(two_trees) -> None:
    """A path rooted in a third worktree cannot be opened from the issue's tree."""
    sibling, issue_tree = two_trees

    result = _attr("resolve_wmbts_for_issue")(ISSUE, control_root=sibling)
    paths = dict(getattr(result, "paths", {}))

    assert paths, "the resolution rendered no paths at all"
    for urn, path in paths.items():
        assert str(path).startswith(str(issue_tree)), (
            f"{urn} rendered as {path}, which is not under the issue's own "
            f"worktree {issue_tree}"
        )


def test_standing_in_the_issues_own_worktree_is_unchanged(two_trees) -> None:
    """The no-regression case: the operator is already where the issue lives."""
    _, issue_tree = two_trees

    tree = _attr("resolve_plan_tree")(ISSUE, control_root=issue_tree)
    result = _attr("resolve_wmbts_for_issue")(ISSUE, control_root=issue_tree)

    assert getattr(tree, "source", None) == "own-worktree"
    assert tree.root == issue_tree
    assert getattr(result, "resolved", None) is True
    assert list(getattr(result, "wmbts", [])) == [ISSUE_BRANCH_WMBT]


def test_the_two_vantage_points_agree(two_trees) -> None:
    """The whole point: the answer no longer depends on where the operator stood."""
    sibling, issue_tree = two_trees
    resolve = _attr("resolve_wmbts_for_issue")

    from_elsewhere = resolve(ISSUE, control_root=sibling)
    from_own = resolve(ISSUE, control_root=issue_tree)

    assert list(from_elsewhere.wmbts) == list(from_own.wmbts), (
        "the same issue reports different WMBTs depending on which worktree the "
        f"command ran in: {list(from_elsewhere.wmbts)} vs {list(from_own.wmbts)}"
    )
    assert from_elsewhere.paths == from_own.paths, (
        "the same issue renders different paths depending on the caller's cwd"
    )


def test_the_render_does_not_qualify_an_answer_it_can_stand_behind(two_trees) -> None:
    """A qualification on every line would train the reader to skip it."""
    sibling, _ = two_trees
    render = _attr("render_wmbt_section")

    text = str(render(_attr("resolve_wmbts_for_issue")(ISSUE, control_root=sibling)))

    assert ISSUE_BRANCH_WMBT in text
    assert "may not be its own tree" not in text, (
        "the banner hedged an answer it resolved through the issue's own binding"
    )
