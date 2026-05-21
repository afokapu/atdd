# URN: test:dispatch-ux-defaults-and-primer:Y004-UNIT-004-render-includes-sibling-context-block
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y004-UNIT-004-render-includes-sibling-context-block
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y004
# Phase: RED
# Layer: unit
# Runtime: python
"""
render() includes a 'Parallel siblings (for context)' block listing sibling
dep numbers. The block must not instruct the agent to wait for siblings to merge.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.session_template import Dependency, IssueContext, render

pytestmark = [pytest.mark.platform]


def _ctx_with_sibling(sibling_num: str = "#20") -> IssueContext:
    return IssueContext(
        number=42,
        branch="feat/demo",
        typed_dependencies=[
            Dependency(number="#10", dep_class="prereq"),
            Dependency(number=sibling_num, dep_class="sibling"),
        ],
    )


def test_sibling_number_appears_in_rendered_output():
    out = render(_ctx_with_sibling("#20"))
    assert "#20" in out


def test_sibling_context_block_present():
    out = render(_ctx_with_sibling("#20"))
    # Must contain some indication it's sibling/parallel context
    assert "sibling" in out.lower() or "parallel" in out.lower()


def test_sibling_block_does_not_say_wait_for_sibling():
    out = render(_ctx_with_sibling("#20"))
    # No line should instruct the agent to wait for #20 specifically
    for line in out.splitlines():
        if "#20" in line:
            assert "wait for #20" not in line.lower(), f"Line instructs wait on sibling: {line}"
            assert "must be merged" not in line.lower(), f"Line blocks on sibling: {line}"


def test_no_sibling_deps_no_sibling_block():
    ctx = IssueContext(
        number=7,
        branch="feat/x",
        typed_dependencies=[Dependency(number="#3", dep_class="prereq")],
    )
    out = render(ctx)
    # Parallel siblings section should not be emitted when there are none
    assert "parallel siblings" not in out.lower()
