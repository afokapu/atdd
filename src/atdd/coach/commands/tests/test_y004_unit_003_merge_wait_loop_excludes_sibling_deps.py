# URN: test:dispatch-ux-defaults-and-primer:Y004-UNIT-003-merge-wait-loop-excludes-sibling-deps
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y004-UNIT-003-merge-wait-loop-excludes-sibling-deps
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y004
# Phase: RED
# Layer: unit
# Runtime: python
"""
render() merge-wait gh pr list search filter includes only prereq dep numbers,
not sibling dep numbers.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.session_template import Dependency, IssueContext, render

pytestmark = [pytest.mark.platform]


def _make_ctx(**kwargs) -> IssueContext:
    defaults = dict(number=42, branch="feat/demo")
    defaults.update(kwargs)
    return IssueContext(**defaults)


def test_prereq_number_appears_in_merge_wait_search():
    ctx = _make_ctx(
        typed_dependencies=[
            Dependency(number="#10", dep_class="prereq"),
            Dependency(number="#20", dep_class="sibling"),
        ]
    )
    out = render(ctx)
    # The gh pr list --search argument in the merge-wait loop must contain #10
    assert "#10" in out


def test_sibling_number_excluded_from_merge_wait_search():
    ctx = _make_ctx(
        typed_dependencies=[
            Dependency(number="#10", dep_class="prereq"),
            Dependency(number="#20", dep_class="sibling"),
        ]
    )
    out = render(ctx)
    # Locate the merge-wait bash block and confirm #20 is not in the --search arg
    lines = out.splitlines()
    in_loop = False
    for line in lines:
        if "while true" in line:
            in_loop = True
        if in_loop and "--search" in line:
            assert "#20" not in line, f"sibling #20 should not be in --search: {line}"
            break


def test_no_siblings_loop_contains_all_prereqs():
    ctx = _make_ctx(
        typed_dependencies=[
            Dependency(number="#5", dep_class="prereq"),
            Dependency(number="#6", dep_class="prereq"),
        ]
    )
    out = render(ctx)
    assert "#5" in out
    assert "#6" in out
    assert "while true" in out
