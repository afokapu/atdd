# URN: test:govern-projection-fields:verify-merge-matrix:C002-UNIT-001-red-matrix-misses-cases
# Acceptance: acc:govern-projection-fields:C002-UNIT-001-red-matrix-misses-cases
# WMBT: wmbt:govern-projection-fields:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: a merge-driver matrix that leaves ownership-rule × divergence-case combinations unexercised is reported by the coverage check, which names each unexercised cell and exits non-zero — so a regression in an untested cell cannot go undetected Refs #1400.
"""An unexercised cell is a blind spot, and the check names it (C002-UNIT-001).

wagon: govern-projection-fields | feature: verify-merge-matrix | phase: RED
WMBT: wmbt:govern-projection-fields:C002

The failure mode is not a merge rule that is wrong. It is a merge rule nobody drove against
one of the four divergence cases — because the first time that combination happens, it
happens during a real merge, on a real branch, and whatever the driver does to the shared
truth is what happens. There is no test to notice.

So the matrix's completeness is itself checked, against the rules the *policy* declares.
"""
from __future__ import annotations

from atdd.state import merge_matrix
from atdd.state.merge_driver import CASE_UNSAFE, DIVERGENCE_CASES
from atdd.state.ownership import RULE_MONOTONIC_GATED, default_policy


def test_c002_unit_001_red_matrix_misses_cases() -> None:
    """A matrix with holes is refused, and every hole is named."""
    # A matrix that exercises phase divergence in every case EXCEPT the unsafe one: the very
    # cell that decides whether an unevidenced GREEN overwrites an honest RED.
    partial = [
        cell for cell in merge_matrix.MATRIX
        if not (cell.rule == RULE_MONOTONIC_GATED and cell.case == CASE_UNSAFE)
    ]

    report = merge_matrix.check_coverage(partial, policy=default_policy())

    assert not report.ok, "a matrix missing a cell must not pass as complete"
    assert (RULE_MONOTONIC_GATED, CASE_UNSAFE) in report.missing
    rendered = report.render()
    assert RULE_MONOTONIC_GATED in rendered and CASE_UNSAFE in rendered
    assert "unexercised" in rendered

    # The check is not merely counting: an empty matrix leaves every declared cell missing.
    empty = merge_matrix.check_coverage([], policy=default_policy())
    assert not empty.ok
    assert len(empty.missing) == len(default_policy().rules()) * len(DIVERGENCE_CASES)
    assert empty.exercised == 0
