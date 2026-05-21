# URN: test:dispatch-ux-defaults-and-primer:Y004-UNIT-002-bare-dep-classified-as-prereq-with-warning-flag
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y004-UNIT-002-bare-dep-classified-as-prereq-with-warning-flag
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y004
# Phase: RED
# Layer: unit
# Runtime: python
"""
A bare #N entry (no tag) is classified as prereq with bare=True.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.session_template import parse_typed_dependencies

pytestmark = [pytest.mark.platform]

BODY_BARE = """### Dependencies

- #100
- #200 — some description but no tag
"""


def test_bare_entry_dep_class_is_prereq():
    deps = parse_typed_dependencies(BODY_BARE)
    by_num = {d.number: d for d in deps}
    assert by_num["#100"].dep_class == "prereq"


def test_bare_entry_bare_flag_is_true():
    deps = parse_typed_dependencies(BODY_BARE)
    by_num = {d.number: d for d in deps}
    assert by_num["#100"].bare is True


def test_bare_entry_with_description_still_bare():
    """'- #200 — some text' has no classification tag; bare=True."""
    deps = parse_typed_dependencies(BODY_BARE)
    by_num = {d.number: d for d in deps}
    assert by_num["#200"].bare is True


def test_tagged_entry_bare_flag_is_false():
    body = "### Dependencies\n\n- #50 (prereq)\n"
    deps = parse_typed_dependencies(body)
    assert deps[0].bare is False
