# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:E031-UNIT-003-kill-scoped-to-issue-handle
# Acceptance: acc:spawn-agents:E031-UNIT-003-kill-scoped-to-issue-handle
# WMBT: wmbt:spawn-agents:E031
# Phase: GREEN
# Layer: backend.application
# Assertion: behavioral
"""E031-UNIT-003 — the kill targets only the respawning issue's worker handle
and never touches another issue's live worker.

RED: fails until ``respawn_worker`` scopes its terminate strictly to the handle
it is given.
"""
from __future__ import annotations

import pytest

from tests.coach._respawn_reliability_helpers import (
    FakeAgentController,
    make_handle,
    make_spec,
)

pytestmark = [pytest.mark.coder]


def test_only_target_issue_handle_is_terminated():
    from atdd.coach.respawn_guards import respawn_worker

    controller = FakeAgentController(die_on_stop=True)
    issue_a_old = make_handle("tester-1079-A", persona="tester")
    issue_b_worker = make_handle("coder-1080-B", persona="coder")
    controller.mark_alive(issue_a_old.agent_id)
    controller.mark_alive(issue_b_worker.agent_id)
    a_next_spec = make_spec("coder-1079-A2", persona="coder")

    respawn_worker(controller, issue_a_old, a_next_spec)

    assert controller.targets_of("stop") == ["tester-1079-A"], (
        "only issue A's worker handle should be terminated"
    )
    assert "coder-1080-B" not in controller.targets_of("stop"), (
        "issue B's worker must not be reaped by issue A's respawn"
    )
    assert controller.is_alive(issue_b_worker) is True, "issue B's worker stays live"
