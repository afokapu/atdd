# URN: test:govern-lifecycle:bind-issue-feature:L003-UNIT-004-an-unseeable-tree-is-its-own-outcome
# Acceptance: acc:govern-lifecycle:L003-UNIT-004-an-unseeable-tree-is-its-own-outcome
# WMBT: wmbt:govern-lifecycle:L003
# Phase: GREEN
# Layer: presentation
# Runtime: python
# Assertion: behavioral
# Purpose: When the issue's tree cannot be located the lookup says so and reads nothing, rather than answering from the cwd's copy or blaming the plan graph for an observation it never made.
"""GREEN test for L003-UNIT-004 — the third outcome.

`#1711` was told, at every one of its five transitions, that its feature "does
not resolve in plan/ — the binding is broken, not absent". The feature was
intact; it was absent only from the worktree the command was standing in, and
the "expected" path in the message named THAT worktree. A confident, precise and
wrong diagnosis of the plan graph, produced by an unmade observation.

So the discriminator here is deliberately adversarial: the tree the command runs
in DOES hold a resolvable feature with WMBTs in it. Anything the lookup prints
that resembles an answer therefore came from a tree it knows is not the issue's.
"""
from __future__ import annotations

import pytest

from ._bind_issue_feature_helpers import (
    FEATURE_URN,
    SIBLING_BRANCH_WMBT,
    control_root,
    make_two_worktree_repo,
    open_store,
    optional_attr,
    seed_issue,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

_RESOLVER_MODULE = "atdd.coach.commands.issue_feature_binding"

UNLOCATED = 96201        # bound to a branch no worktree holds
NO_BRANCH = 96202        # records no branch at all
ABSENT_BRANCH = "feat/checked-out-nowhere-on-this-machine"


def _attr(name):
    fn = optional_attr(_RESOLVER_MODULE, name)
    assert fn is not None, f"expected {_RESOLVER_MODULE}.{name}"
    return fn


@pytest.fixture()
def sibling_only(tmp_path):
    """One checkout, holding a perfectly resolvable feature that is not the issue's."""
    sibling, _ = make_two_worktree_repo(tmp_path, issue_branch="feat/unused-here")
    write_plan_tree(sibling, wmbts=(SIBLING_BRANCH_WMBT,))
    store = open_store(sibling)
    seed_issue(
        store, slug="unlocated-probe", issue_number=UNLOCATED,
        feature=FEATURE_URN, extra={"branch": ABSENT_BRANCH},
    )
    seed_issue(
        store, slug="no-branch-probe", issue_number=NO_BRANCH,
        feature=FEATURE_URN, extra={"branch": None},
    )
    return sibling


def test_an_unlocatable_tree_is_a_distinct_outcome(sibling_only) -> None:
    result = _attr("resolve_wmbts_for_issue")(UNLOCATED, control_root=sibling_only)

    assert getattr(result, "resolved", None) is False
    assert getattr(result, "reason", None) == "unlocated", (
        "'I cannot see the issue's tree' was folded into another outcome; "
        f"reason={getattr(result, 'reason', None)!r}"
    )
    assert getattr(result, "tree", None) is not None
    assert result.tree.root is None, (
        "a tree was still handed to the resolver even though none could be located"
    )


def test_it_reads_nothing_rather_than_the_cwds_copy(sibling_only) -> None:
    """The cwd holds a resolvable feature. Answering from it is the defect."""
    result = _attr("resolve_wmbts_for_issue")(UNLOCATED, control_root=sibling_only)

    assert list(getattr(result, "wmbts", [])) == [], (
        f"the lookup answered with {list(result.wmbts)} — read out of the tree the "
        "command was standing in, which it knows is not the issue's"
    )
    assert dict(getattr(result, "paths", {})) == {}, (
        "paths were rendered for a tree that could not be located"
    )


def test_it_does_not_blame_the_plan_graph_for_an_observation_it_never_made(
    sibling_only,
) -> None:
    """#1711's harm: told the decomposition was corrupt when it was correct."""
    render = _attr("render_wmbt_section")

    text = str(render(_attr("resolve_wmbts_for_issue")(UNLOCATED, control_root=sibling_only)))

    assert "binding is broken" not in text, (
        "the banner still reports a plan-graph fault for a lookup that could not "
        f"look:\n{text}"
    )
    assert "none found" not in text.lower()
    assert ABSENT_BRANCH in text, (
        "the message does not name the branch whose tree could not be found, so "
        f"the reader cannot act on it:\n{text}"
    )
    assert str(sibling_only / "plan") not in text, (
        "the message names a path under the cwd's plan/ as where the artefact was "
        "expected — the #1711 sentence that sent a reader to fix a file in the "
        f"wrong worktree:\n{text}"
    )


def test_an_issue_with_no_branch_still_answers_but_says_whose_tree_it_read(
    sibling_only,
) -> None:
    """Nothing to resolve THROUGH is not the same as knowing the tree is wrong.

    A bare count computed from an unrelated tree is not acceptable even when no
    better tree exists (#1732 Decisions), so the answer is qualified rather than
    withheld — withholding it would strand every issue before worktree-create.
    """
    resolve = _attr("resolve_wmbts_for_issue")
    render = _attr("render_wmbt_section")

    result = resolve(NO_BRANCH, control_root=sibling_only)

    assert getattr(result, "resolved", None) is True
    assert list(result.wmbts) == [SIBLING_BRANCH_WMBT]
    assert result.tree.source == "unbound-branch"

    text = str(render(result))
    assert "may not be its own tree" in text, (
        f"the count was printed bare, with nothing saying which tree produced it:\n{text}"
    )


def test_outside_a_git_working_tree_nothing_is_qualified(tmp_path) -> None:
    """A hermetic dir or a pre-`git init` consumer repo has no other tree to confuse.

    This is the clause that keeps every pre-existing caller behaving exactly as
    it did: with no VCS there are no branches, so cwd is not a *choice*.
    """
    root = control_root(tmp_path)
    write_plan_tree(root, wmbts=(SIBLING_BRANCH_WMBT,))
    seed_issue(
        open_store(root), slug="hermetic-probe", issue_number=96203,
        feature=FEATURE_URN, extra={"branch": ABSENT_BRANCH},
    )

    result = _attr("resolve_wmbts_for_issue")(96203, control_root=root)

    assert result.tree.source == "no-vcs"
    assert result.resolved is True
    assert list(result.wmbts) == [SIBLING_BRANCH_WMBT]
    assert "may not be its own tree" not in str(_attr("render_wmbt_section")(result))


def test_git_being_unrunnable_qualifies_rather_than_crashes(sibling_only, monkeypatch) -> None:
    """A missing tool must not turn a banner into an outage — nor into a claim.

    "git is not on PATH" says nothing about whether sibling worktrees exist; it
    says only that we could not ask. So the answer is given AND qualified, which
    is a different sentence from the unqualified `no-vcs` one above.
    """
    import atdd.coach.utils.git as coach_git

    def _no_git(*_args, **_kwargs):
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(coach_git.subprocess, "run", _no_git)

    result = _attr("resolve_wmbts_for_issue")(UNLOCATED, control_root=sibling_only)

    assert result.tree.source == "no-git"
    assert result.resolved is True, "a missing git took the whole lookup down"
    assert list(result.wmbts) == [SIBLING_BRANCH_WMBT]
    assert "git could not be run" in str(_attr("render_wmbt_section")(result))
