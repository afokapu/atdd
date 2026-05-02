"""
Topological-sort engine tests for `atdd merge-cascade --dry-run`.

Issue #365: DAG-aware merge cascade with dry-run.

Public surface under test:
- ``compute_merge_order(pr_numbers, fetch_diff, extra_deps=None) -> list[int]``
- ``MergeCascadeCycleError`` (raised on cycle, exposes ``cycle_path``)

Design:
- Edge signal = shared file overlap in PR diffs (Decision #1 in the issue).
- Tie-break = ascending PR number (Decision #2).
- Edge orientation under file-overlap: lower PR → higher PR (acyclic by
  construction; matches the "older PR was authored first" intuition).
- ``extra_deps`` is the injection hook used by tests and the cycle fixture
  to construct cycles for cycle-detection coverage.

SPEC IDs: SPEC-COACH-ORCH-0008 (DAG topology), SPEC-COACH-ORCH-0009 (cycle
detection).
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.merge_cascade_topology import (
    MergeCascadeCycleError,
    compute_merge_order,
)

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _diffs(mapping: dict[int, set[str]]):
    """Build a fetch_diff callable from a static dict."""
    return lambda pr: mapping.get(pr, set())


# ---------------------------------------------------------------------------
# compute_merge_order — empty / singleton / disjoint
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_list():
    assert compute_merge_order([], _diffs({})) == []


def test_single_pr_returns_singleton():
    assert compute_merge_order([7], _diffs({7: {"pyproject.toml"}})) == [7]


def test_disjoint_prs_sort_by_pr_number_ascending():
    """No shared files → ordering falls back to ascending PR number."""
    diffs = {
        300: {"a.py"},
        301: {"b.py"},
        302: {"c.py"},
    }
    assert compute_merge_order([302, 300, 301], _diffs(diffs)) == [300, 301, 302]


# ---------------------------------------------------------------------------
# compute_merge_order — file-overlap edges
# ---------------------------------------------------------------------------


def test_shared_file_creates_lower_to_higher_edge():
    """When two PRs share a file, the lower PR number merges first."""
    diffs = {
        301: {"pyproject.toml"},
        300: {"pyproject.toml"},
    }
    assert compute_merge_order([301, 300], _diffs(diffs)) == [300, 301]


def test_chain_through_shared_pyproject():
    """Every PR touches pyproject.toml → strict ascending chain."""
    diffs = {pr: {"pyproject.toml"} for pr in (350, 351, 352, 353)}
    assert compute_merge_order(
        [353, 351, 350, 352], _diffs(diffs)
    ) == [350, 351, 352, 353]


def test_partial_overlap_preserves_independent_branches():
    """
    300 and 301 share a file (must be sequential).
    400 is independent of both — it should slot in by PR-number tie-break.
    """
    diffs = {
        300: {"foo.py"},
        301: {"foo.py"},
        400: {"bar.py"},
    }
    order = compute_merge_order([400, 301, 300], _diffs(diffs))
    # 300 must come before 301
    assert order.index(300) < order.index(301)
    # All three present
    assert sorted(order) == [300, 301, 400]
    # Deterministic: with ascending tie-break, 300 < 400 wins at level 0
    assert order == [300, 301, 400]


def test_deterministic_across_input_orderings():
    """compute_merge_order must be input-order-independent."""
    diffs = {
        100: {"x.py"},
        200: {"x.py"},
        300: {"y.py"},
        400: {"x.py", "y.py"},
    }
    a = compute_merge_order([100, 200, 300, 400], _diffs(diffs))
    b = compute_merge_order([400, 300, 200, 100], _diffs(diffs))
    c = compute_merge_order([300, 100, 400, 200], _diffs(diffs))
    assert a == b == c


# ---------------------------------------------------------------------------
# MergeCascadeCycleError — explicit-dep injection
# ---------------------------------------------------------------------------


def test_cycle_pair_raises_with_path():
    """A→B and B→A explicit deps must raise MergeCascadeCycleError."""
    diffs = {1: set(), 2: set()}
    extra_deps = {1: {2}, 2: {1}}
    with pytest.raises(MergeCascadeCycleError) as exc_info:
        compute_merge_order([1, 2], _diffs(diffs), extra_deps=extra_deps)
    cycle = exc_info.value.cycle_path
    assert set(cycle) == {1, 2}
    # cycle_path should close on itself for readability
    assert cycle[0] == cycle[-1]


def test_cycle_message_lists_path():
    diffs = {1: set(), 2: set(), 3: set()}
    extra_deps = {1: {3}, 2: {1}, 3: {2}}  # 1→3→2→1
    with pytest.raises(MergeCascadeCycleError) as exc_info:
        compute_merge_order([1, 2, 3], _diffs(diffs), extra_deps=extra_deps)
    message = str(exc_info.value)
    for pr in (1, 2, 3):
        assert f"#{pr}" in message


def test_extra_deps_respected_when_acyclic():
    """extra_deps adds edges on top of file-overlap ones; result still topo-sorted."""
    diffs = {1: set(), 2: set(), 3: set()}
    # Force 3 to merge before 1 even though 1 < 3
    extra_deps = {1: {3}}
    order = compute_merge_order([1, 2, 3], _diffs(diffs), extra_deps=extra_deps)
    assert order.index(3) < order.index(1)


# ---------------------------------------------------------------------------
# MergeCascadeCycleError — instantiation
# ---------------------------------------------------------------------------


def test_cycle_error_exposes_cycle_path_attribute():
    err = MergeCascadeCycleError([1, 2, 1])
    assert err.cycle_path == [1, 2, 1]
    assert "#1" in str(err) and "#2" in str(err)
