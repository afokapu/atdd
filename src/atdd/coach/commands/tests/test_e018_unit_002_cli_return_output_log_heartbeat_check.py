# URN: test:spawn-agents:E018-UNIT-002-cli-return-output-log-heartbeat-check
# Acceptance: acc:spawn-agents:E018-UNIT-002-cli-return-output-log-heartbeat-check
# WMBT: wmbt:spawn-agents:E018
# Phase: GREEN
# Assertion: behavioral
"""E018-UNIT-002 — in cli-return mode, _verify_process_alive also polls
agents/<id>/output.log for at least 1 byte; raises ProcessNotAlive if log
stays empty while the process appears alive.

RED: fails until ProcessNotAlive and _verify_process_alive exist with cli-return logic.
"""
from __future__ import annotations

import time
import threading
from pathlib import Path

import pytest


class _AliveProc:
    def poll(self):
        return None


class _DeadProc:
    def poll(self):
        return 1


def test_cli_return_mode_raises_when_output_log_empty(tmp_path):
    from atdd.coach.commands.spawn import ProcessNotAlive, _verify_process_alive

    agent_dir = tmp_path / "agents" / "planner-857-nolog"
    agent_dir.mkdir(parents=True)
    # output.log does not exist — shim never emitted a heartbeat

    with pytest.raises(ProcessNotAlive):
        _verify_process_alive(
            proc=_AliveProc(),
            agent_id="planner-857-nolog",
            runtime_dir=agent_dir,
            transport="cli-return",
            timeout_s=0.1,
        )


def test_cli_return_mode_no_raise_when_output_log_has_content(tmp_path):
    from atdd.coach.commands.spawn import _verify_process_alive

    agent_dir = tmp_path / "agents" / "planner-857-haslog"
    agent_dir.mkdir(parents=True)
    output_log = agent_dir / "output.log"
    output_log.write_bytes(b"shim started\n")

    _verify_process_alive(
        proc=_AliveProc(),
        agent_id="planner-857-haslog",
        runtime_dir=agent_dir,
        transport="cli-return",
        timeout_s=0.5,
    )
    # Must not raise


def test_non_cli_return_mode_ignores_missing_output_log(tmp_path):
    from atdd.coach.commands.spawn import _verify_process_alive

    agent_dir = tmp_path / "agents" / "planner-857-nocheck"
    # Do NOT create agent_dir or output.log
    # In non-cli-return mode, absence of output.log must not raise

    _verify_process_alive(
        proc=_AliveProc(),
        agent_id="planner-857-nocheck",
        runtime_dir=agent_dir,
        transport="",
        timeout_s=0.1,
    )
    # Must not raise


def test_cli_return_raises_when_proc_also_dead(tmp_path):
    from atdd.coach.commands.spawn import ProcessNotAlive, _verify_process_alive

    agent_dir = tmp_path / "agents" / "planner-857-both-dead"
    agent_dir.mkdir(parents=True)
    # proc is dead AND output.log is empty — should still raise ProcessNotAlive

    with pytest.raises(ProcessNotAlive):
        _verify_process_alive(
            proc=_DeadProc(),
            agent_id="planner-857-both-dead",
            runtime_dir=agent_dir,
            transport="cli-return",
            timeout_s=0.1,
        )


def test_cli_return_output_log_written_during_poll_window(tmp_path):
    """output.log written within the timeout window => no raise."""
    from atdd.coach.commands.spawn import _verify_process_alive

    agent_dir = tmp_path / "agents" / "planner-857-delayed"
    agent_dir.mkdir(parents=True)
    output_log = agent_dir / "output.log"

    def _write_after_delay():
        time.sleep(0.05)
        output_log.write_bytes(b"shim started after short delay\n")

    writer = threading.Thread(target=_write_after_delay, daemon=True)
    writer.start()

    _verify_process_alive(
        proc=_AliveProc(),
        agent_id="planner-857-delayed",
        runtime_dir=agent_dir,
        transport="cli-return",
        timeout_s=1.0,
        poll_interval_s=0.02,
    )
    writer.join(timeout=2.0)
    # Must not raise (log appeared within timeout)
