# URN: test:govern-projection-fields:verify-merge-matrix:C002-UNIT-002-green-every-cell-exercised
# Acceptance: acc:govern-projection-fields:C002-UNIT-002-green-every-cell-exercised
# WMBT: wmbt:govern-projection-fields:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: every merge rule the committed policy declares is driven against every divergence case (identical, no-op, evidence-backed, unsafe) through the real merge driver — each of the 32 cells asserting a merged result or a named conflict, never an unasserted pass — the coverage check exits zero, and a newly declared merge rule with no cells fails it Refs #1400.
"""Every cell of the matrix is exercised against the real driver (C002-UNIT-002).

wagon: govern-projection-fields | feature: verify-merge-matrix | phase: RED
WMBT: wmbt:govern-projection-fields:C002

This is the matrix actually being *driven*, not merely counted: every (merge rule ×
divergence case) cell goes through :func:`atdd.state.merge_driver.merge_object` and has to
produce what it says it produces — a merged document with the value it names, or a conflict
under the rule it names. A cell that asserted nothing would be a hole with a test in front
of it, so the coverage check treats an unasserted cell as missing.

And the property that keeps this from rotting: the rule set comes from the **policy**. Add a
merge rule to the policy and its four cells do not exist yet — so the check fails until
somebody writes them, which is the only way a matrix stays complete as a policy grows.
"""
from __future__ import annotations

import pytest

from atdd.state import merge_driver, merge_matrix
from atdd.state.merge_matrix import EXPECT_CONFLICT, EXPECT_MERGED, MATRIX
from atdd.state.ownership import DEFAULT_POLICY, FieldOwnershipPolicy, default_policy


@pytest.mark.parametrize("cell", MATRIX, ids=lambda c: f"{c.rule}:{c.case}")
def test_c002_unit_002_green_every_cell_exercised(cell) -> None:
    """Each cell drives the real driver and asserts a merged result or a named conflict."""
    policy = default_policy()

    result = merge_driver.merge_object(
        merge_matrix.UID, cell.base, cell.ours, cell.theirs,
        policy=policy,
        ours_evidence=cell.ours_evidence,
        theirs_evidence=cell.theirs_evidence,
    )

    assert cell.expect in (EXPECT_MERGED, EXPECT_CONFLICT), "a cell must assert an outcome"

    if cell.expect == EXPECT_MERGED:
        assert result.ok, f"{cell.rule} × {cell.case} must merge ({cell.note}): {result.render()}"
        assert result.merged is not None
        assert result.merged[cell.field] == cell.merged_value
    else:
        assert not result.ok, f"{cell.rule} × {cell.case} must conflict ({cell.note})"
        assert result.merged is None, "a conflicted merge produces no document at all"
        conflicted = {conflict.field for conflict in result.conflicts}
        assert cell.field in conflicted
        # The conflict is reported under a rule, and a rule an operator can look up.
        assert all(conflict.rule for conflict in result.conflicts)

    # The matrix as a whole covers every cell the policy declares.
    report = merge_matrix.check_coverage(policy=policy)
    assert report.ok, report.render()
    assert report.exercised == report.total == len(policy.rules()) * 4

    # ...and a newly declared merge rule, with no cells written for it, fails the check.
    grown = FieldOwnershipPolicy.from_document({
        "fields": [*DEFAULT_POLICY["fields"],
                   {"field": "next_field", "writer": "core_authoring", "rule": "eventual-consistency"}],
    })
    grown_report = merge_matrix.check_coverage(policy=grown)
    assert not grown_report.ok
    assert ("eventual-consistency", "identical") in grown_report.missing
