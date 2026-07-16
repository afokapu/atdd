# URN: test:consolidate-coach-workspace:enforce-surface-conformance:E004-INTEGRATION-001-validator-flags-non-role-name
# Acceptance: acc:consolidate-coach-workspace:E004-INTEGRATION-001-validator-flags-non-role-name
# WMBT: wmbt:consolidate-coach-workspace:E004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E004-INTEGRATION-001 — the bound naming validator flags a non-role-aware
managed surface name and accepts a conforming one, and binds its rule via
bind_rule (the binding contract). Recognition reuses the #470 primitive.

#1486: the observer was decommissioned, so the ``ObserverRule`` wrapper
(``predicate``/``apply_correction``) is gone and the recogniser was rehomed to
``atdd.coach.utils.canonical_role_naming``. The rule and its flagging semantics
are unchanged — these assertions now drive the pure recogniser directly.
"""
from __future__ import annotations

from atdd.coach.utils import canonical_role_naming


def test_validator_binds_the_rule():
    # The bound validator module binds the role-aware rule at import time.
    from atdd.coach.validators import test_canonical_role_naming as bound

    assert bound._RULE.rule_id == "coach.session.canonical-role-name"


def test_flags_only_non_role_aware_names():
    events = [
        {"type": "surface_state", "ref": "surface:1", "name": "ATDD865-worker-coach-layout"},
        {"type": "surface_state", "ref": "surface:2", "name": "ATDD865-coach-layout"},
    ]
    # drift fires because surface:2 lacks the <role> segment
    assert canonical_role_naming.flag_non_conforming(events) == ["surface:2"]


def test_all_role_aware_names_pass_clean():
    events = [
        {"type": "surface_state", "ref": "surface:1", "name": "ATDD865-worker-coach-layout"},
        {"type": "surface_state", "ref": "surface:2", "name": "ATDD601-coach-daemon-mux-parity"},
        {"type": "surface_state", "ref": "surface:3", "name": "ATDD730-phase2-observer-persistent-surface"},
    ]
    assert canonical_role_naming.flag_non_conforming(events) == []
