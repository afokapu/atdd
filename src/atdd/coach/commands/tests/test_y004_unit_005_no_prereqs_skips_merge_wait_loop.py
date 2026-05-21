# URN: test:dispatch-ux-defaults-and-primer:Y004-UNIT-005-no-prereqs-skips-merge-wait-loop
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y004-UNIT-005-no-prereqs-skips-merge-wait-loop
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y004
# Phase: RED
# Layer: unit
# Runtime: python
"""
When all deps are siblings (no prereqs), render() omits the merge-wait loop
and emits a begin-immediately note instead.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.session_template import Dependency, IssueContext, render

pytestmark = [pytest.mark.platform]


def _all_sibling_ctx() -> IssueContext:
    return IssueContext(
        number=42,
        branch="feat/demo",
        typed_dependencies=[
            Dependency(number="#20", dep_class="sibling"),
            Dependency(number="#30", dep_class="sibling"),
        ],
    )


def test_no_while_loop_when_only_siblings():
    out = render(_all_sibling_ctx())
    assert "while true" not in out


def test_begin_immediately_note_present():
    out = render(_all_sibling_ctx())
    low = out.lower()
    assert "begin planning immediately" in low or "begin immediately" in low or "no prerequisites" in low


def test_no_deps_at_all_also_skips_loop():
    ctx = IssueContext(number=5, branch="feat/y", typed_dependencies=[])
    out = render(ctx)
    assert "while true" not in out


def test_mixed_deps_still_emits_loop():
    ctx = IssueContext(
        number=9,
        branch="feat/z",
        typed_dependencies=[
            Dependency(number="#1", dep_class="prereq"),
            Dependency(number="#2", dep_class="sibling"),
        ],
    )
    out = render(ctx)
    assert "while true" in out
