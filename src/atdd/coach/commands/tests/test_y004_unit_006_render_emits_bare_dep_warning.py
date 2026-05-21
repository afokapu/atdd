# URN: test:dispatch-ux-defaults-and-primer:Y004-UNIT-006-render-emits-bare-dep-warning
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y004-UNIT-006-render-emits-bare-dep-warning
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y004
# Phase: RED
# Layer: unit
# Runtime: python
"""
render() includes a warning comment when any dep entry is bare (no tag).
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.session_template import Dependency, IssueContext, render

pytestmark = [pytest.mark.platform]


def _bare_ctx() -> IssueContext:
    return IssueContext(
        number=42,
        branch="feat/demo",
        typed_dependencies=[
            Dependency(number="#99", dep_class="prereq", bare=True),
        ],
    )


def test_bare_dep_triggers_warning_in_output():
    out = render(_bare_ctx())
    low = out.lower()
    # The rendered output must warn about the bare dep
    assert "warning" in low or "bare" in low or "untagged" in low or "tag" in low


def test_bare_dep_warning_mentions_dep_number():
    out = render(_bare_ctx())
    # The warning should reference the bare dep so the operator knows which to fix
    assert "#99" in out


def test_no_bare_deps_no_warning():
    ctx = IssueContext(
        number=1,
        branch="feat/a",
        typed_dependencies=[
            Dependency(number="#5", dep_class="prereq", bare=False),
        ],
    )
    out = render(ctx)
    low = out.lower()
    # No bare deps → no warning comment block about bare/untagged entries
    assert "untagged" not in low
    assert "bare" not in low


def test_warning_recommends_tagging():
    out = render(_bare_ctx())
    low = out.lower()
    # The warning should recommend the operator add a tag
    assert "(prereq)" in low or "(sibling)" in low or "tag" in low
