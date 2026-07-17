# URN: test:govern-registry:E002-UNIT-001-cross-registry-collision-raises-with-precedence
# Acceptance: acc:govern-registry:E002-UNIT-001-cross-registry-collision-raises-with-precedence
# WMBT: wmbt:govern-registry:E002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:E002-UNIT-001-cross-registry-collision-raises-with-precedence.

A rule_id present in both the core and the extension set raises DuplicateRuleError
whose message names the colliding id and states CORE precedes extension; disjoint
sets do not raise.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.rule_binding import DuplicateRuleError
from atdd.enforce.registry import assert_core_precedes_extension


def test_cross_registry_collision_raises_with_precedence() -> None:
    core_ids = {"coder.dead-code.reachability", "coder.security.sql-injection"}
    extension_ids = {"coder.dead-code.reachability"}  # collides with core

    with pytest.raises(DuplicateRuleError) as exc:
        assert_core_precedes_extension(core_ids, extension_ids)
    message = str(exc.value)
    assert "coder.dead-code.reachability" in message
    assert "CORE precedes extension" in message

    # Disjoint registries → no collision, no raise.
    assert (
        assert_core_precedes_extension(
            {"coder.a.one"}, {"coder.b.two"}
        )
        is None
    )
