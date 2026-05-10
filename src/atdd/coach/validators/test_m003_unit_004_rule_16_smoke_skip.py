# URN: component:observe-and-correct:observer-runtime-and-rules:test_m003_unit_004_rule_16_smoke_skip:backend:domain
# Runtime: python
# Purpose: Reverse-coherence binding for coach.observer.smoke-skip (rule 16).

"""Validator wrapper for observer rule 16 (issue #513).

Binds ``coach.observer.smoke-skip`` and asserts the absorption-pattern
parity between the rule and the SMOKE-skip clause of
``babysit.detect_violation`` per spec §0.2. Detailed parity tests live at
``src/atdd/coach/commands/tests/test_m003_unit_004_rule_16_smoke_skip.py``.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands import babysit, observer
from atdd.coach.observer_rules import smoke_skip
from atdd.coach.utils.rule_binding import bind_rule


_RULE = bind_rule("coach.observer.smoke-skip")


pytestmark = [pytest.mark.coach]


def test_rule_16_parity_with_detect_violation():
    """Rule 16 fires only for the SMOKE-skip clause of detect_violation."""
    assert _RULE.rule_id == "coach.observer.smoke-skip"

    # Absorption: verbatim helper per spec §0.2.
    assert smoke_skip.detect_violation is babysit.detect_violation

    # Fire: --status REFACTOR with no SMOKE in screen.
    screen = "agent ran: atdd issue 513 --status REFACTOR\n"
    baseline = babysit.detect_violation(screen)
    assert baseline is not None and baseline.matched == "SMOKE skip"
    assert smoke_skip.predicate(
        observer.ObservedInput(
            agent_id="agent-A",
            log_lines=tuple(screen.splitlines()),
        )
    ) is True

    # No-fire: GREEN→SMOKE→REFACTOR trajectory (SMOKE present in screen).
    safe_screen = (
        "ran: atdd issue 513 --status SMOKE\n"
        "all SMOKE tests passed\n"
        "ran: atdd issue 513 --status REFACTOR\n"
    )
    assert smoke_skip.predicate(
        observer.ObservedInput(
            agent_id="agent-A",
            log_lines=tuple(safe_screen.splitlines()),
        )
    ) is False

    # No-fire on the OTHER variant of detect_violation (.atdd/ hand-edit) —
    # rule 16 owns ONLY the SMOKE-skip clause.
    hand_edit_screen = "ran: Edit .atdd/manifest.yaml\n"
    other = babysit.detect_violation(hand_edit_screen)
    assert other is not None and other.matched == ".atdd/ hand-edit"
    assert smoke_skip.predicate(
        observer.ObservedInput(
            agent_id="agent-A",
            log_lines=tuple(hand_edit_screen.splitlines()),
        )
    ) is False
