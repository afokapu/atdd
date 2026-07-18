# URN: test:govern-lifecycle:smoke-false-green-prevention:E028-UNIT-002-convention-has-producer-only-rule
# Acceptance: acc:govern-lifecycle:E028-UNIT-002-convention-has-producer-only-rule
# WMBT: wmbt:govern-lifecycle:E028
# Phase: RED
# Layer: unit
# Assertion: structural
"""
RED: smoke.convention.yaml must contain an anti-pattern rule mandating that
SMOKE tests assert on operator-observable behavior, not on intermediate producer
artifacts (output.log existence, file write events).  Currently fails because
the rule has not been added to the convention yet.
"""
from __future__ import annotations

import pytest
from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.planner, pytest.mark.platform]

_CONVENTION_PATH = (
    find_repo_root() / "src" / "atdd" / "tester" / "conventions" / "smoke.convention.yaml"
)
_REQUIRED_TERMS = ["operator-observable", "output.log"]


def test_convention_has_producer_only_assertion_rule():
    """smoke.convention.yaml must contain the producer-only-assertion anti-pattern rule."""
    assert _CONVENTION_PATH.exists(), (
        f"smoke.convention.yaml not found at {_CONVENTION_PATH}"
    )
    content = _CONVENTION_PATH.read_text()
    for term in _REQUIRED_TERMS:
        assert term in content, (
            f"smoke.convention.yaml is missing term '{term}'. "
            "Add the producer-only-assertion anti-pattern rule: SMOKE tests MUST assert "
            "on operator-observable behavior, not on intermediate-artifact-write events "
            "(output.log existence, cli-return.jsonl file write)."
        )
