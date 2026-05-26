# URN: test:govern-lifecycle:smoke-false-green-prevention:E028-UNIT-003-convention-has-handoff-coverage-rule
# Acceptance: acc:govern-lifecycle:E028-UNIT-003-convention-has-handoff-coverage-rule
# WMBT: wmbt:govern-lifecycle:E028
# Phase: RED
# Layer: unit
# Assertion: structural
"""
RED: smoke.convention.yaml must contain an anti-pattern rule requiring that when
a feature has a producer→consumer handoff, the SMOKE must exercise both ends in
a single test.  Currently fails because the rule has not been added yet.
"""
from __future__ import annotations

import pytest
from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.planner]

_CONVENTION_PATH = (
    find_repo_root() / "src" / "atdd" / "tester" / "conventions" / "smoke.convention.yaml"
)
_REQUIRED_TERMS = ["handoff", "producer", "consumer"]


def test_convention_has_cross_component_handoff_rule():
    """smoke.convention.yaml must contain the cross-component handoff-coverage rule."""
    assert _CONVENTION_PATH.exists(), (
        f"smoke.convention.yaml not found at {_CONVENTION_PATH}"
    )
    content = _CONVENTION_PATH.read_text()
    for term in _REQUIRED_TERMS:
        assert term in content, (
            f"smoke.convention.yaml is missing term '{term}'. "
            "Add the cross-component handoff rule: when a feature has a producer→consumer "
            "handoff, the SMOKE MUST exercise both ends in a single test."
        )
