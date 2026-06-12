# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:E031-UNIT-001-kill-precedes-relaunch-on-transition
# Acceptance: acc:spawn-agents:E031-UNIT-001-kill-precedes-relaunch-on-transition
# WMBT: wmbt:spawn-agents:E031
# Phase: GREEN
# Layer: backend.application
# Assertion: behavioral
"""E031-UNIT-001 — on a phase transition the prior worker is terminated BEFORE
the next persona is launched, and no CLI-specific quit literal is sent.

RED: fails until ``respawn_worker`` exists in ``atdd.coach.respawn_guards`` and
orders the kill (signal + stop) strictly before the relaunch spawn, scoped to
the prior worker's handle.
"""
from __future__ import annotations

import pytest

from tests.coach._respawn_reliability_helpers import (
    FakeAgentController,
    make_handle,
    make_spec,
)

pytestmark = [pytest.mark.coder]


def test_terminate_recorded_before_relaunch_spawn():
    from atdd.coach.respawn_guards import respawn_worker

    controller = FakeAgentController(die_on_stop=True)
    old = make_handle("tester-1079-old", persona="tester")
    next_spec = make_spec("coder-1079-new", persona="coder")

    respawn_worker(controller, old, next_spec)

    ops = controller.op_names()
    assert "stop" in ops and "spawn" in ops, f"expected both stop and spawn, got {ops}"
    assert ops.index("stop") < ops.index("spawn"), (
        f"the prior worker must be terminated BEFORE the next persona is launched: {ops}"
    )


def test_terminate_targets_the_prior_worker_handle_exactly_once():
    from atdd.coach.respawn_guards import respawn_worker

    controller = FakeAgentController(die_on_stop=True)
    old = make_handle("tester-1079-old", persona="tester")
    next_spec = make_spec("coder-1079-new", persona="coder")

    respawn_worker(controller, old, next_spec)

    assert controller.targets_of("stop") == ["tester-1079-old"], (
        "exactly one stop, targeting the prior worker handle"
    )


def test_no_cli_specific_quit_literal_is_sent():
    from atdd.coach.respawn_guards import respawn_worker

    controller = FakeAgentController(die_on_stop=True)
    old = make_handle("tester-1079-old", persona="tester")
    next_spec = make_spec("coder-1079-new", persona="coder")

    respawn_worker(controller, old, next_spec)

    # The kill is CLI-agnostic — via the agent_control abstraction, never a
    # hardcoded '/exit' delivered as a prompt/keystroke.
    delivered = [c for c in controller.calls if c[0] == "deliver_prompt"]
    assert delivered == [], f"no prompt/quit literal should be delivered: {delivered}"
