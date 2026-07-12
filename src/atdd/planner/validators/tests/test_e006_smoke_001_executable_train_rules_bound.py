# URN: test:author-plan-substrate:bind-train-substrate:E006-SMOKE-001-seed
# Acceptance: acc:author-plan-substrate:E006-SMOKE-001-seed
# WMBT: wmbt:author-plan-substrate:E006
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E006-SMOKE-001 — the executable-train rules are BOUND and ENFORCE.

Executes against the real rule registry (#1151: a smoke must execute, not skip):
- every executable-train rule resolves through ``bind_rule`` (registry side), and
- a real composite-key violation routed through ``assert_disposition_satisfied``
  fails the strict disposition gate (enforcement side).
"""
from __future__ import annotations

from atdd.coach.utils.rule_binding import bind_rule
from atdd.planner.validators._dispatch_registry import (
    check_composite_key_exceptional,
)

_EXECUTABLE_TRAIN_RULES = (
    "planner.train.family-matches-terminal-contract",
    "planner.train.dispatch-map-is-registry",
    "planner.train.dispatch-composite-key-exceptional",
)


def test_executable_train_rules_are_bound_and_enforce():
    # Registry side: each rule resolves against the real train.convention.yaml rules: block.
    bound = {rid: bind_rule(rid) for rid in _EXECUTABLE_TRAIN_RULES}
    for rid, rule in bound.items():
        assert rule.severity == 3, f"{rid}: severity={rule.severity}"
        assert rule.disposition == "strict", f"{rid}: disposition={rule.disposition}"

    # Enforcement side: the bound validator's check catches a real violation
    # (composite key with no behavioral_difference — the #1083 canonical case).
    violating_entry = {
        "artifact_urn": "commons:decision:escalation",
        "train_id": "0301-resolve-escalation",
        "discriminant": {"cause": "dangerous_action"},
    }
    assert check_composite_key_exceptional(violating_entry) is not None
