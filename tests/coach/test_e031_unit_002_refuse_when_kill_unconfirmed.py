# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:E031-UNIT-002-refuse-when-kill-unconfirmed
# Acceptance: acc:spawn-agents:E031-UNIT-002-refuse-when-kill-unconfirmed
# WMBT: wmbt:spawn-agents:E031
# Phase: GREEN
# Layer: backend.application
# Assertion: behavioral
"""E031-UNIT-002 — when the prior worker cannot be confirmed dead, the transition
refuses and never launches the next persona (no two live agents on one issue).

RED: fails until ``respawn_worker`` confirms liveness via the controller and
refuses (no spawn) when the worker is still alive after the kill.
"""
from __future__ import annotations

import pytest

from tests.coach._respawn_reliability_helpers import (
    FakeAgentController,
    make_handle,
    make_spec,
)

pytestmark = [pytest.mark.coder]


def test_no_relaunch_spawn_when_worker_stays_alive():
    from atdd.coach.respawn_guards import respawn_worker

    # die_on_stop=False → is_alive(old) stays True after stop(): the kill fails.
    controller = FakeAgentController(die_on_stop=False)
    old = make_handle("tester-1079-old", persona="tester")
    controller.mark_alive(old.agent_id)
    next_spec = make_spec("coder-1079-new", persona="coder")

    outcome = respawn_worker(controller, old, next_spec)

    assert "spawn" not in controller.op_names(), (
        "a failed kill must NOT be followed by a relaunch — that stacks a 2nd live agent"
    )
    assert getattr(outcome, "refused", False) is True, "outcome must record a refusal"
    assert getattr(outcome, "relaunched", True) is False


def test_refusal_records_the_unreaped_handle():
    from atdd.coach.respawn_guards import respawn_worker

    controller = FakeAgentController(die_on_stop=False)
    old = make_handle("tester-1079-old", persona="tester")
    controller.mark_alive(old.agent_id)
    next_spec = make_spec("coder-1079-new", persona="coder")

    outcome = respawn_worker(controller, old, next_spec)

    assert "tester-1079-old" in (getattr(outcome, "reason", "") or ""), (
        "the refusal reason must name the un-reaped worker handle"
    )
