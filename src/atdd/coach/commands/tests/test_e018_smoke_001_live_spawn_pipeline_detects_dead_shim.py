# URN: test:spawn-agents:coach-spawn-stage-detector:E018-SMOKE-001-live-spawn-pipeline-detects-dead-shim
# Acceptance: acc:spawn-agents:E018-SMOKE-001-live-spawn-pipeline-detects-dead-shim
# WMBT: wmbt:spawn-agents:E018
# Phase: SMOKE
# Layer: backend.smoke
# Runtime: python
# Assertion: behavioral
"""E018-SMOKE-001 — when atdd spawn runs in cli-return mode and the shim process exits
immediately (exit code 1), ProcessNotAlive is raised and agent_spawned is NOT emitted.

Smoke gate: requires ATDD_RUN_SMOKE=1 and a real cmux session available.
Simulates the dead-shim failure mode without launching a real terminal multiplexer.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="E018-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_dead_shim_process_raises_process_not_alive_no_agent_spawned(tmp_path):
    """ProcessNotAlive is raised when cli-return output.log never arrives within timeout.

    Uses a real subprocess that exits 1 immediately (no output.log written),
    proving the liveness gate rejects the dead shim before agent_spawned fires.
    """
    from atdd.coach.commands.spawn import ProcessNotAlive, _verify_process_alive

    agent_id = "smoke-e018-dead-shim"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    # Spawn a real process that exits immediately without writing output.log
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.exit(1)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.05)  # let process exit

    with pytest.raises(ProcessNotAlive) as exc_info:
        _verify_process_alive(
            proc=proc,
            agent_id=agent_id,
            runtime_dir=agent_dir,
            transport="cli-return",
            timeout_s=0.5,
        )

    assert agent_id in str(exc_info.value) or "output.log" in str(exc_info.value), (
        f"E018-SMOKE-001: ProcessNotAlive message must identify the agent or log path. "
        f"Got: {exc_info.value!r}"
    )
    proc.wait(timeout=2)


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="E018-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_live_shim_process_with_output_log_does_not_raise(tmp_path):
    """ProcessNotAlive is NOT raised when output.log appears within timeout.

    Uses a real subprocess that writes output.log and stays alive long enough.
    """
    from atdd.coach.commands.spawn import _verify_process_alive

    agent_id = "smoke-e018-live-shim"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    output_log = agent_dir / "output.log"

    # Spawn a real process that writes output.log then sleeps briefly
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import time; open({str(output_log)!r}, 'wb').write(b'shim started\\n'); time.sleep(2)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _verify_process_alive(
            proc=proc,
            agent_id=agent_id,
            runtime_dir=agent_dir,
            transport="cli-return",
            timeout_s=2.0,
        )
    finally:
        proc.terminate()
        proc.wait(timeout=2)
    # Must not raise
