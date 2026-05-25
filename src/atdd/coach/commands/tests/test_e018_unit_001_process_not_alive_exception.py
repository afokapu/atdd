# URN: test:spawn-agents:E018-UNIT-001-process-not-alive-exception
# Acceptance: acc:spawn-agents:E018-UNIT-001-process-not-alive-exception
# WMBT: wmbt:spawn-agents:E018
# Phase: GREEN
# Assertion: behavioral
"""E018-UNIT-001 — ProcessNotAlive is raised when the shim process exits before
the process-alive stage timeout; the exception message contains the exit code.

RED: fails until ProcessNotAlive and _verify_process_alive exist in spawn.py.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


class _DeadProc:
    """Fake process object whose poll() immediately returns 1 (exited)."""

    def poll(self):
        return 1


class _AliveProc:
    """Fake process object whose poll() always returns None (still running)."""

    def poll(self):
        return None


def test_process_not_alive_raised_when_proc_exits():
    from atdd.coach.commands.spawn import ProcessNotAlive, _verify_process_alive

    with pytest.raises(ProcessNotAlive) as exc_info:
        _verify_process_alive(
            proc=_DeadProc(),
            agent_id="planner-857-dead",
            runtime_dir=Path("/tmp/rt/agents/planner-857-dead"),
            transport="",
            timeout_s=0.1,
        )
    assert "1" in str(exc_info.value), (
        f"ProcessNotAlive message must contain exit code '1', got: {exc_info.value!r}"
    )


def test_process_not_alive_is_subclass_of_worker_readiness_timeout():
    from atdd.coach.commands.spawn import ProcessNotAlive, WorkerReadinessTimeout

    assert issubclass(ProcessNotAlive, WorkerReadinessTimeout), (
        "ProcessNotAlive must be a subclass of WorkerReadinessTimeout"
    )


def test_no_raise_when_proc_is_alive(tmp_path):
    from atdd.coach.commands.spawn import _verify_process_alive

    # Non-cli-return mode: only poll() check, no output.log requirement.
    _verify_process_alive(
        proc=_AliveProc(),
        agent_id="planner-857-alive",
        runtime_dir=tmp_path / "agents" / "planner-857-alive",
        transport="",
        timeout_s=0.1,
    )
    # Must not raise


def test_exception_message_contains_agent_id():
    from atdd.coach.commands.spawn import ProcessNotAlive, _verify_process_alive

    with pytest.raises(ProcessNotAlive) as exc_info:
        _verify_process_alive(
            proc=_DeadProc(),
            agent_id="planner-857-named",
            runtime_dir=Path("/tmp/rt/agents/planner-857-named"),
            transport="",
            timeout_s=0.1,
        )
    assert "planner-857-named" in str(exc_info.value), (
        f"Exception message must contain agent_id, got: {exc_info.value!r}"
    )
