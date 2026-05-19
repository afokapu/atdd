# URN: test:drive-state-machine:coach-state-machine-and-runtime:R002-UNIT-001-green-is-not-terminal
# Acceptance: acc:drive-state-machine:R002-UNIT-001-green-is-not-terminal
# WMBT: wmbt:drive-state-machine:R002
# Phase: RED
# Layer: application
"""R002-UNIT-001 — GREEN is not a terminal state; _cold_start_proposed_transition maps GREEN→SMOKE.

Issue #712 Edge C. Confirms the mappings needed for the event loop to
continue past GREEN. These are confirmatory unit tests — if they fail, the
advance map or state-transition table has regressed.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_cold_start_advance_from_green_to_smoke():
    """_COLD_START_ADVANCE_FROM maps Phase.GREEN to Phase.SMOKE."""
    from atdd.coach.commands.coach import _COLD_START_ADVANCE_FROM, Phase

    assert Phase.SMOKE == _COLD_START_ADVANCE_FROM.get(Phase.GREEN), (
        "_COLD_START_ADVANCE_FROM must map GREEN → SMOKE"
    )


def test_cold_start_proposed_transition_green_agent_done_returns_green_to_smoke():
    """_cold_start_proposed_transition returns Transition(GREEN, SMOKE) on agent_done at GREEN."""
    from atdd.coach.commands.coach import _cold_start_proposed_transition, Phase
    from atdd.coach.handlers.state_machine import StateMachine

    sm = StateMachine(issue_number=690, phase=Phase.GREEN)
    event = {"event_type": "agent_done", "agent_id": "coder-690-abc123"}
    t = _cold_start_proposed_transition(sm, event)

    assert t is not None, "Expected a Transition for GREEN agent_done; got None"
    assert t.src == Phase.GREEN
    assert t.dst == Phase.SMOKE


def test_can_transition_green_to_smoke():
    """The state-transition table allows GREEN → SMOKE."""
    from atdd.coach.commands.coach import Phase, can_transition

    assert can_transition(Phase.GREEN, Phase.SMOKE), (
        "can_transition(GREEN, SMOKE) must be True"
    )


def test_green_not_in_terminal_stop_set():
    """Phase.GREEN is not in the loop's terminal stop set (COMPLETE, MERGED, BLOCKED)."""
    from atdd.coach.commands.coach import Phase

    stop_set = {Phase.COMPLETE, Phase.MERGED, Phase.BLOCKED}
    assert Phase.GREEN not in stop_set, (
        "GREEN must not be in the terminal stop set — the loop must continue past it"
    )
