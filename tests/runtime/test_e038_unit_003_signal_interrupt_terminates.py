# URN: test:govern-lifecycle:extract-runtime-agent-control-and-close-spawn-cluster:E038-UNIT-003-signal-interrupt-terminates
# Acceptance: acc:govern-lifecycle:E038-UNIT-003-signal-interrupt-terminates
# WMBT: wmbt:govern-lifecycle:E038
# Phase: RED
# Assertion: behavioral
# Layer: runtime
"""E038-UNIT-003 — signal(INTERRUPT) terminates the wrapped agent (closes #871).

docs/coach-decomposition.md §4.8: ``signal`` "Including stdin forwarding for
INTERRUPT (closes #871 — stdin gap)". A real child process is wrapped in a real
pty; AgentSignal.INTERRUPT must reach it and terminate it.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _spec(runtime_dir: Path, agent_id: str):
    from atdd.runtime.agent_control import DispatchSpec

    agent_dir = runtime_dir / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    return DispatchSpec(
        agent_id=agent_id,
        persona="coder",
        worktree_path=runtime_dir,
        prompt_text="launch",
        correction_inbox=agent_dir / "cli-return.jsonl",
        output_log=agent_dir / "output.log",
        runtime_dir=runtime_dir,
        env_overrides={},
        transport="cli-return",
        permission_mode="acceptEdits",
        allowed_tools=(),
    )


def _wait_until(predicate, timeout_s=5.0, interval=0.05):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_signal_interrupt_terminates_wrapped_agent(tmp_path):
    from atdd.runtime.agent_control import AgentSignal, ShimAgentController

    controller = ShimAgentController()
    spec = _spec(tmp_path, "coder-871-a")

    # A real child that blocks indefinitely until interrupted.
    handle = controller.spawn(
        spec,
        agent_command=[sys.executable, "-c", "import time\nwhile True:\n    time.sleep(0.2)"],
    )
    try:
        assert _wait_until(lambda: controller.is_alive(handle)), "agent never came alive"

        controller.signal(handle, AgentSignal.INTERRUPT)

        assert _wait_until(
            lambda: not controller.is_alive(handle)
        ), "agent still alive after INTERRUPT"
    finally:
        controller.stop(handle, reason="test-teardown")
