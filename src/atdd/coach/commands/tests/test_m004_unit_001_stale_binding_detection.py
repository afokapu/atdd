# URN: test:govern-lifecycle:govern-lifecycle:M004-UNIT-001-a-binding-to-a-missing-directory-is-reported-and-a-live-one-is-not
# Acceptance: acc:govern-lifecycle:M004-UNIT-001-a-binding-to-a-missing-directory-is-reported-and-a-live-one-is-not
# WMBT: wmbt:govern-lifecycle:M004
# Phase: RED
# Layer: application
"""M004-UNIT-001 — a binding is stale when its DIRECTORY is gone. Nothing else.

The tempting shortcuts are all wrong, and each is asserted against here:

  * a COMPLETE work item is not drift — the phase says nothing about whether the
    directory exists, and a finished issue whose worktree is still checked out is
    a perfectly ordinary state;
  * a merged branch is not drift for the same reason;
  * a work item with NO worktree_path is not drift either — that is the untracked
    half of #1529, it needs an operator, and reporting it here would mix a
    mechanical fix with a judgement call.

Pure over a set of records and an existence predicate, so it runs without a store.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.worktree_bindings import stale_bindings


@pytest.mark.coder
def test_a_binding_to_a_missing_directory_is_reported(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    gone = tmp_path / "gone"          # never created

    items = [
        {"slug": "has-live", "worktree_path": str(live)},
        {"slug": "has-gone", "worktree_path": str(gone)},
    ]

    reported = {b.slug for b in stale_bindings(items)}

    assert reported == {"has-gone"}, (
        "only the binding whose directory is absent is drift; a live worktree is "
        f"a real one: {reported}"
    )


@pytest.mark.coder
def test_a_work_item_with_no_binding_is_not_reported(tmp_path):
    """An ABSENT binding is the inverse defect and belongs to #1529's other half."""
    items = [
        {"slug": "unbound"},
        {"slug": "empty", "worktree_path": ""},
        {"slug": "null", "worktree_path": None},
    ]

    assert list(stale_bindings(items)) == [], (
        "a work item carrying no worktree_path asserts nothing false — reporting "
        "it would mix an operator judgement into a mechanical clear"
    )


@pytest.mark.coder
@pytest.mark.parametrize("state", ["COMPLETE", "OBSOLETE", "REFACTOR"])
def test_phase_does_not_make_a_live_directory_stale(tmp_path, state):
    """The phase is not evidence about the filesystem."""
    live = tmp_path / "still-here"
    live.mkdir()

    items = [{"slug": "done", "status": state, "worktree_path": str(live)}]

    assert list(stale_bindings(items)) == [], (
        f"a {state} work item whose directory still exists is not drift — the "
        "check keys on the directory, not the lifecycle"
    )


@pytest.mark.coder
def test_the_report_carries_what_an_operator_needs_to_act(tmp_path):
    gone = tmp_path / "gone"
    items = [{"slug": "wi-42", "worktree_path": str(gone)}]

    (binding,) = list(stale_bindings(items))

    assert binding.slug == "wi-42"
    assert binding.path == str(gone), "the report must name the path it found absent"
