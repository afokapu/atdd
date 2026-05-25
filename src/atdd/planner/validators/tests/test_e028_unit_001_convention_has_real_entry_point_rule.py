# URN: test:govern-lifecycle:smoke-false-green-prevention:E028-UNIT-001-convention-has-real-entry-point-rule
# Acceptance: acc:govern-lifecycle:E028-UNIT-001-convention-has-real-entry-point-rule
# WMBT: wmbt:govern-lifecycle:E028
# Phase: RED
# Layer: unit
# Assertion: structural
"""
RED: smoke.convention.yaml must contain an anti-pattern rule mandating that
SMOKE tests drive the real CLI entry point (not a synthetic stub).  Currently
fails because the rule has not been added to the convention yet.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.planner]

_CONVENTION_PATH = (
    find_repo_root() / "src" / "atdd" / "tester" / "conventions" / "smoke.convention.yaml"
)
# Keywords that must appear together in the convention to satisfy the rule
_REQUIRED_TERMS = ["real-entry-point", "synthetic"]


def test_convention_has_real_entry_point_rule():
    """smoke.convention.yaml must contain the real-entry-point anti-pattern rule."""
    assert _CONVENTION_PATH.exists(), (
        f"smoke.convention.yaml not found at {_CONVENTION_PATH}"
    )
    content = _CONVENTION_PATH.read_text()
    for term in _REQUIRED_TERMS:
        assert term in content, (
            f"smoke.convention.yaml is missing term '{term}'. "
            "Add the real-entry-point anti-pattern rule: SMOKE tests MUST drive the real "
            "CLI entry point, not a synthetic subprocess stub (cat, sleep, FakeMultiplexer)."
        )
