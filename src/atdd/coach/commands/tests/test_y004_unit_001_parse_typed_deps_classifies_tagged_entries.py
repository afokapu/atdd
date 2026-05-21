# URN: test:dispatch-ux-defaults-and-primer:Y004-UNIT-001-parse-typed-deps-classifies-tagged-entries
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y004-UNIT-001-parse-typed-deps-classifies-tagged-entries
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y004
# Phase: RED
# Layer: unit
# Runtime: python
"""
parse_typed_dependencies classifies (sibling)/(parallel) tags as 'sibling'
and (prereq)/(merged) tags as 'prereq'.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.session_template import parse_typed_dependencies

pytestmark = [pytest.mark.platform]

BODY_WITH_TAGS = """## Scope

### Dependencies

- #10 (prereq) — infrastructure shipped
- #20 (merged) — already closed
- #30 (sibling) — parallel work same wave
- #40 (parallel) — another parallel issue
"""


def test_prereq_tag_classified_correctly():
    deps = parse_typed_dependencies(BODY_WITH_TAGS)
    by_num = {d.number: d for d in deps}
    assert by_num["#10"].dep_class == "prereq"


def test_merged_tag_classified_as_prereq():
    deps = parse_typed_dependencies(BODY_WITH_TAGS)
    by_num = {d.number: d for d in deps}
    assert by_num["#20"].dep_class == "prereq"


def test_sibling_tag_classified_correctly():
    deps = parse_typed_dependencies(BODY_WITH_TAGS)
    by_num = {d.number: d for d in deps}
    assert by_num["#30"].dep_class == "sibling"


def test_parallel_tag_classified_as_sibling():
    deps = parse_typed_dependencies(BODY_WITH_TAGS)
    by_num = {d.number: d for d in deps}
    assert by_num["#40"].dep_class == "sibling"


def test_all_four_entries_returned():
    deps = parse_typed_dependencies(BODY_WITH_TAGS)
    nums = [d.number for d in deps]
    assert "#10" in nums
    assert "#20" in nums
    assert "#30" in nums
    assert "#40" in nums


def test_tags_case_insensitive():
    body = "### Dependencies\n\n- #99 (SIBLING)\n- #88 (PREREQ)\n"
    deps = parse_typed_dependencies(body)
    by_num = {d.number: d for d in deps}
    assert by_num["#99"].dep_class == "sibling"
    assert by_num["#88"].dep_class == "prereq"
