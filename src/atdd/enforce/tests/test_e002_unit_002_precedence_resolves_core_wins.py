# URN: test:govern-registry:E002-UNIT-002-precedence-resolves-core-wins
# Acceptance: acc:govern-registry:E002-UNIT-002-precedence-resolves-core-wins
# WMBT: wmbt:govern-registry:E002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:E002-UNIT-002-precedence-resolves-core-wins.

When a unified view is unavoidable the stated precedence resolves it — the core
declaration of a colliding rule_id wins over the extension mirror — and
DuplicateRuleError is a genuine raisable exception (previously named nowhere).
"""
from __future__ import annotations

from atdd.coach.utils.rule_binding import DuplicateRuleError
from atdd.enforce.registry import merge_with_precedence


def test_precedence_resolves_core_wins() -> None:
    core_registry = {"coder.dead-code.reachability": {"severity": 4, "origin": "core"}}
    extension_registry = {
        "coder.dead-code.reachability": {"severity": 3, "origin": "extension"}
    }

    merged = merge_with_precedence(core_registry, extension_registry)

    # Core precedes extension: the colliding entry resolves to the CORE body.
    assert merged["coder.dead-code.reachability"] == {"severity": 4, "origin": "core"}

    # DuplicateRuleError is a real, raisable exception type.
    assert issubclass(DuplicateRuleError, Exception)
    try:
        raise DuplicateRuleError("boom")
    except DuplicateRuleError as exc:
        assert str(exc) == "boom"
