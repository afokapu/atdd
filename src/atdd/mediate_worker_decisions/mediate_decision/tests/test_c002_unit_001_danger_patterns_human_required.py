# URN: test:mediate-worker-decisions:mediate-decision:C002-UNIT-001-danger-patterns-human-required
# Acceptance: acc:mediate-worker-decisions:C002-UNIT-001-danger-patterns-human-required
# WMBT: wmbt:mediate-worker-decisions:C002
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C002-UNIT-001 — every danger pattern -> human_required; safe -> auto."""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.mediate_decision.src.domain.safety_classifier import classify


@pytest.mark.parametrize("label", [
    "git push to origin", "git merge main", "gh pr merge 5",
    "rm -rf build", "force push the branch", "run a destructive migration",
])
def test_danger_is_human_required(label):
    sc = classify("Proceed?", [label, "do nothing"])
    assert not sc.is_safe
    assert sc.matched_rule is not None


def test_ordinary_is_safe():
    sc = classify("Pick a name?", ["add a unit test", "rename the function"])
    assert sc.is_safe
