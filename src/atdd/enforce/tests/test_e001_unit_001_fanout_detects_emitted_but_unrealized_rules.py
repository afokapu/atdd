# URN: test:bind-extension-conventions:bind-extension-conventions:E001-UNIT-001-fanout-detects-emitted-but-unrealized-rules
# Acceptance: acc:bind-extension-conventions:E001-UNIT-001-fanout-detects-emitted-but-unrealized-rules
# WMBT: wmbt:bind-extension-conventions:E001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""RED Test for acc:bind-extension-conventions:E001-UNIT-001-fanout-detects-emitted-but-unrealized-rules.

The fan-out helper reports every rule a detector emits but does not yet realize,
and reports none once ``realizes_convention`` lists the full emitted set.
"""
from __future__ import annotations

from atdd.enforce.fanout import under_bound_rules


def test_fanout_detects_emitted_but_unrealized_rules() -> None:
    # A multi-rule detector realizing one convention but emitting three rules.
    scalar = {"realizes_convention": "x", "emits_rule_ids": ["x", "y", "z"]}
    assert under_bound_rules(scalar) == {"y", "z"}

    # Once realizes_convention lists all three, nothing is under-bound.
    fanned = {"realizes_convention": ["x", "y", "z"], "emits_rule_ids": ["x", "y", "z"]}
    assert under_bound_rules(fanned) == set()
