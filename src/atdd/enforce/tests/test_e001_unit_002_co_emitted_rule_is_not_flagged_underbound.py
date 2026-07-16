# URN: test:bind-extension-conventions:bind-extension-conventions:E001-UNIT-002-co-emitted-rule-is-not-flagged-underbound
# Acceptance: acc:bind-extension-conventions:E001-UNIT-002-co-emitted-rule-is-not-flagged-underbound
# WMBT: wmbt:bind-extension-conventions:E001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""RED Test for acc:bind-extension-conventions:E001-UNIT-002-co-emitted-rule-is-not-flagged-underbound.

Ownership fans out, but co-emission does not. A rule a detector emits yet does
not OWN (``coder.logging.structured`` co-emits ``coder.logging.print``, which the
dedicated print detector owns) is excluded from the under-bound set, so the
fan-out never binds a rule to the wrong detector.
"""
from __future__ import annotations

from atdd.enforce.fanout import under_bound_rules


def test_co_emitted_rule_is_not_flagged_underbound() -> None:
    impl = {
        "realizes_convention": ["coder.logging.structured"],
        "emits_rule_ids": ["coder.logging.structured", "coder.logging.print"],
    }

    # With the co-emitted rule declared as not-owned, it is NOT under-bound.
    assert under_bound_rules(impl, co_emitted={"coder.logging.print"}) == set()

    # Without the exclusion the emitted-but-unrealized rule WOULD be flagged —
    # proving the exclusion, not an empty emit set, is what suppresses it.
    assert under_bound_rules(impl) == {"coder.logging.print"}
