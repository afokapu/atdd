# URN: test:drive-state-machine:phase-advance-requires-completion-match:E002-UNIT-003-agent-done-advances-only-on-persona-phase-match
# Acceptance: acc:drive-state-machine:E002-UNIT-003-agent-done-advances-only-on-persona-phase-match
# WMBT: wmbt:drive-state-machine:E002
# Phase: RED
# Harness: unit
# Layer: domain
"""E002-UNIT-003 — agent_done advances only when the completing persona's phase == sm.phase.

Issue #1055. The ``agent_done`` branch of
``coach.py::_cold_start_proposed_transition`` matches only the issue number
(``parts[1]``) and advances from ``sm.phase``, ignoring the COMPLETING persona
(``parts[0]``). A durable/replayed planner done.json keeps re-firing a
PLANNED-completion while the SM sits at RED, re-advancing on every run — RED is
permanently skipped.

The fix mirrors the ``commit_observed`` guard (``completed != sm.phase`` →
return None): derive the completed phase from the persona prefix and advance only
when it equals ``sm.phase``.

This test pins that gate with a ``tester`` agent_done (tester completes RED):
  * sm.phase == GREEN → completed (RED) != GREEN → returns None (no advance)
  * sm.phase == RED   → completed (RED) == RED   → returns Transition(RED, GREEN)

RED until the persona→phase guard exists: on current code the agent_done branch
advances from sm.phase regardless of persona, so the GREEN case wrongly returns
Transition(GREEN, SMOKE) instead of None.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.coach import _cold_start_proposed_transition
from atdd.coach.handlers.state_machine import Phase, StateMachine

pytestmark = [pytest.mark.platform]


def test_tester_done_while_sm_at_green_does_not_advance():
    """A tester-done (completes RED) must NOT advance an SM sitting at GREEN."""
    sm = StateMachine(issue_number=1051, phase=Phase.GREEN)
    t = _cold_start_proposed_transition(
        sm, {"event_type": "agent_done", "agent_id": "tester-1051-abc1234"}
    )
    assert t is None, (
        "A tester-done completes RED, not GREEN; with the SM at GREEN the agent_done "
        f"branch must return None (no advance). Got {t!r}"
    )


def test_tester_done_while_sm_at_red_advances_to_green():
    """A tester-done (completes RED) advances an SM sitting at RED to GREEN."""
    sm = StateMachine(issue_number=1051, phase=Phase.RED)
    t = _cold_start_proposed_transition(
        sm, {"event_type": "agent_done", "agent_id": "tester-1051-abc1234"}
    )
    assert t is not None, "tester-done at RED must advance"
    assert t.src == Phase.RED and t.dst == Phase.GREEN, (
        f"Expected Transition(RED, GREEN); got {t.src}→{t.dst}"
    )


def test_planner_done_while_sm_at_red_does_not_advance():
    """A replayed planner-done (completes PLANNED) must NOT advance an SM at RED.

    This is the exact live #1051 replay: a durable planner done.json re-fires while
    the SM sits at RED and must be ignored, not advanced RED→GREEN.
    """
    sm = StateMachine(issue_number=1051, phase=Phase.RED)
    t = _cold_start_proposed_transition(
        sm, {"event_type": "agent_done", "agent_id": "planner-1051-5ba26310"}
    )
    assert t is None, (
        "A planner-done completes PLANNED, not RED; with the SM at RED it must "
        f"return None (no advance). Got {t!r}"
    )
