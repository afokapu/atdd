# URN: test:spawn-agents:E021-SMOKE-001-live-process-alive-message-names-polled-path
# Acceptance: acc:spawn-agents:E021-SMOKE-001-live-process-alive-message-names-polled-path
# WMBT: wmbt:spawn-agents:E021
# Phase: SMOKE
# Layer: backend.smoke
# Runtime: python
# Assertion: behavioral
"""E021-SMOKE-001 — the deployed _verify_process_alive produces a ProcessNotAlive
message that includes the absolute path being polled; confirmed against the live
installed package.

Smoke gate: requires ATDD_RUN_SMOKE=1.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke]


class _AliveProc:
    def poll(self):
        return None


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="E021-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_deployed_verify_process_alive_names_polled_path_in_message(tmp_path):
    from atdd.coach.commands.spawn import ProcessNotAlive, _verify_process_alive

    agent_id = "smoke-e021-path-msg"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    # output.log does not exist

    with pytest.raises(ProcessNotAlive) as exc_info:
        _verify_process_alive(
            proc=_AliveProc(),
            agent_id=agent_id,
            runtime_dir=agent_dir,
            transport="cli-return",
            timeout_s=0.1,
        )

    msg = str(exc_info.value)
    expected_log_path = str(agent_dir / "output.log")

    assert expected_log_path in msg, (
        f"E021-SMOKE-001: ProcessNotAlive message must name the absolute polled path. "
        f"Expected {expected_log_path!r} in message. Got: {msg!r}"
    )


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="E021-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_deployed_verify_process_alive_message_is_actionable(tmp_path):
    from atdd.coach.commands.spawn import ProcessNotAlive, _verify_process_alive

    agent_id = "smoke-e021-actionable"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    with pytest.raises(ProcessNotAlive) as exc_info:
        _verify_process_alive(
            proc=_AliveProc(),
            agent_id=agent_id,
            runtime_dir=agent_dir,
            transport="cli-return",
            timeout_s=0.1,
        )

    msg = str(exc_info.value)
    # Message must provide actionable path information, not just "crashed silently"
    # without context. The path must appear in the message.
    assert "/" in msg, (
        f"E021-SMOKE-001: ProcessNotAlive message must contain a path (with '/') "
        f"to be actionable. Got: {msg!r}"
    )
    # The agent_id should appear to identify which agent timed out.
    assert agent_id in msg or "output.log" in msg, (
        f"E021-SMOKE-001: message must identify the agent or log path. Got: {msg!r}"
    )
