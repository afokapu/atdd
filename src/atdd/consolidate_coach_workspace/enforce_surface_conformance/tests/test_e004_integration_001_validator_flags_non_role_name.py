# URN: test:consolidate-coach-workspace:enforce-surface-conformance:E004-INTEGRATION-001-validator-flags-non-role-name
# Acceptance: acc:consolidate-coach-workspace:E004-INTEGRATION-001-validator-flags-non-role-name
# WMBT: wmbt:consolidate-coach-workspace:E004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E004-INTEGRATION-001 — the bound naming validator flags a non-role-aware
managed surface name and accepts a conforming one, and binds its rule via
bind_rule (the binding contract). Recognition is the role-aware drift family
(extends canonical_naming_drift), reusing the #470 primitive."""
from __future__ import annotations

from atdd.coach.observer_rules import canonical_role_naming
from atdd.coach.commands import observer


def test_validator_binds_the_rule():
    # The bound validator module binds the role-aware rule at import time.
    from atdd.coach.validators import test_canonical_role_naming as bound

    assert bound._RULE.rule_id == "coach.session.canonical-role-name"


def test_predicate_flags_only_non_role_aware_names():
    ctx = observer.ObservedInput(
        agent_id="test-865",
        events=[
            {"type": "surface_state", "ref": "surface:1", "name": "ATDD865-worker-coach-layout"},
            {"type": "surface_state", "ref": "surface:2", "name": "ATDD865-coach-layout"},
        ]
    )
    # drift fires because surface:2 lacks the <role> segment
    assert canonical_role_naming.predicate(ctx) is True

    flagged = canonical_role_naming.flag_non_conforming(ctx.events)
    assert flagged == ["surface:2"]


def test_all_role_aware_names_pass_clean():
    ctx = observer.ObservedInput(
        agent_id="test-865",
        events=[
            {"type": "surface_state", "ref": "surface:1", "name": "ATDD865-worker-coach-layout"},
            {"type": "surface_state", "ref": "surface:2", "name": "ATDD601-coach-daemon-mux-parity"},
            {"type": "surface_state", "ref": "surface:3", "name": "ATDD730-phase2-observer-persistent-surface"},
        ]
    )
    assert canonical_role_naming.predicate(ctx) is False
    assert canonical_role_naming.flag_non_conforming(ctx.events) == []
