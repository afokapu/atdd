# URN: test:govern-lifecycle:subissue-label-check-examines-every-parent:E080-UNIT-001-every-parent-is-examined
# Acceptance: acc:govern-lifecycle:E080-UNIT-001-every-parent-is-examined
# WMBT: wmbt:govern-lifecycle:E080
# Phase: GREEN
# Layer: backend.unit
"""E080-UNIT-001 — the sub-issue label check examines every parent (#1907).

It used to `return` after the first parent that had sub-issues, annotated
"# Found and validated — pass". Reading the source shows it stops early. What
reading does NOT show is the consequence a spike measured:

    {dirty, clean}  -> FAIL      correct
    {clean, dirty}  -> PASS      same data, opposite verdict

The verdict depended on ITERATION ORDER. An order-dependent gate is worse than a
blind one: it goes green and red across runs with no code change, and every green
is believed. Measured on the live repository: it examined 1 of 12 parents, and 36
sub-issues sat unlabelled behind it.

A second defect surfaced once the `return` was removed — the trailing
`pytest.skip` then fired on every clean run, so a fully-labelled repository would
report SKIPPED and never PASSED. NOT_APPLICABLE is "no parent has sub-issues at
all", and nothing else.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators.test_C001_roundtrip import (
    test_wmbt_sub_issues_have_atdd_wmbt_label as check,
)

pytestmark = [pytest.mark.coach]


def _sub(number: int, labelled: bool) -> dict:
    return {
        "number": number,
        "title": f"sub {number}",
        "labels": [{"name": "atdd-wmbt"}] if labelled else [],
    }


CLEAN = [_sub(10, True), _sub(11, True)]
DIRTY = [_sub(20, False)]


def _verdict(data: dict) -> str:
    try:
        check(data)
    except pytest.skip.Exception:
        return "SKIP"
    except AssertionError:
        return "FAIL"
    return "PASS"


def test_drift_in_the_first_parent_is_caught() -> None:
    assert _verdict({1: DIRTY, 2: CLEAN}) == "FAIL"


def test_drift_in_a_LATER_parent_is_caught() -> None:
    """THE DEFECT. Identical data to the case above, reordered — and it passed."""
    assert _verdict({1: CLEAN, 2: DIRTY}) == "FAIL"


def test_the_verdict_does_not_depend_on_order() -> None:
    """Stated separately because order-dependence is the property that made every
    green untrustworthy, not merely some of them."""
    assert _verdict({1: DIRTY, 2: CLEAN}) == _verdict({1: CLEAN, 2: DIRTY})


def test_drift_behind_several_clean_parents_is_caught() -> None:
    assert _verdict({1: CLEAN, 2: CLEAN, 3: CLEAN, 4: DIRTY}) == "FAIL"


def test_every_drifted_parent_is_reported_not_just_the_first() -> None:
    """It used to stop at the first, so an operator fixed one and met the next on
    the following run."""
    with pytest.raises(AssertionError) as excinfo:
        check({1: DIRTY, 2: DIRTY, 3: DIRTY})
    # Asserted on the header, not by counting occurrences: pytest's assertion
    # rewriting appends the repr of the accumulator, so every entry appears twice
    # and a naive count reads 6 for 3 parents.
    assert "3 of 3 parent issue(s)" in str(excinfo.value)


def test_a_fully_labelled_repository_PASSES() -> None:
    """Not skips. Removing the early return left the trailing skip firing on
    every clean run, so the check could never say "I looked and it is fine"."""
    assert _verdict({1: CLEAN, 2: CLEAN}) == "PASS"


def test_a_parent_with_no_sub_issues_is_skipped_over_not_stopped_at() -> None:
    assert _verdict({1: [], 2: DIRTY}) == "FAIL"


@pytest.mark.parametrize("data", [{}, {1: [], 2: []}])
def test_no_parent_with_sub_issues_is_not_applicable(data: dict) -> None:
    """The one legitimate skip: there is genuinely nothing to check."""
    assert _verdict(data) == "SKIP"
