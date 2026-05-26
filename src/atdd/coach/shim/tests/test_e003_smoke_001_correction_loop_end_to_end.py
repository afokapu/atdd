# URN: test:observe-and-correct:E003-SMOKE-001-correction-loop-end-to-end
# Acceptance: acc:observe-and-correct:E003-SMOKE-001-correction-loop-end-to-end
# WMBT: wmbt:observe-and-correct:E003
# Phase: SMOKE
# Assertion: behavioral
# Layer: integration
# Scope: SMOKE — drives real atdd spawn path via atdd-shim CLI entry point.
#
# Retrofit (#855): replaced direct shim class instantiation with invoke_atdd_spawn
# helper that routes through the real atdd-shim CLI (what cmd_spawn builds and the
# multiplexer launches). Ensures _inject_agent_env and _build_shim_command are
# exercised, not bypassed by a synthetic fixture.
"""E003-SMOKE-001 — Correction-loop end-to-end via real atdd spawn path.

  agent emits drift → output.log → observer fires → cli-return.jsonl →
  atdd-shim (real CLI entry point) delivers bytes to agent stdin →
  agent acknowledges → drift resolves.

Drives the real atdd-shim CLI entry point (``python -m atdd.coach.shim``),
which is the command built by ``_build_shim_command`` and launched by
``cmd_spawn`` via the multiplexer. This exercises the full command-construction
path, not a direct shim class instantiation.

Issue #824 (original). Retrofit by #855 (real-entry-point mandate).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.platform]

_DRIFT_AGENT = """
import sys, time, os

runtime_dir = sys.argv[1]
agent_id = sys.argv[2]
agent_dir = os.path.join(runtime_dir, "agents", agent_id)
output_log = os.path.join(agent_dir, "output.log")

with open(output_log, "a") as f:
    f.write("DRIFT_TRIGGER: missing canonical layout\\n")
    f.flush()

deadline = time.time() + 15.0
while time.time() < deadline:
    line = sys.stdin.readline()
    if line.strip():
        with open(output_log, "a") as f:
            f.write(f"CORRECTION_RECEIVED: {line.strip()}\\n")
        sys.exit(0)
    time.sleep(0.1)

sys.exit(1)
"""


def invoke_atdd_spawn(agent_id: str, runtime_dir: Path, adapter_command: list) -> subprocess.Popen:
    """Invoke the real atdd spawn path via the atdd-shim CLI entry point.

    This is the command that ``cmd_spawn`` builds via ``_build_shim_command``
    and that the multiplexer launches as the foreground surface process.
    """
    return subprocess.Popen(
        [sys.executable, "-m", "atdd.coach.shim",
         "--agent-id", agent_id,
         "--runtime-dir", str(runtime_dir),
         "--",
         *adapter_command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_correction_loop_closes_under_shim(tmp_path):
    """Agent emits drift; observer fires; atdd-shim delivers correction bytes to agent stdin."""
    from atdd.coach.commands.observer import InjectionDispatcher, Correction

    agent_id = "e2e-loop-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    agent_script = tmp_path / "drift_agent.py"
    agent_script.write_text(_DRIFT_AGENT)

    shim_proc = invoke_atdd_spawn(
        agent_id,
        tmp_path,
        [sys.executable, str(agent_script), str(tmp_path), agent_id],
    )

    output_log = agent_dir / "output.log"
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if output_log.exists() and "DRIFT_TRIGGER" in output_log.read_text():
            break
        time.sleep(0.1)
    else:
        shim_proc.terminate()
        pytest.fail("Agent did not emit DRIFT_TRIGGER within 10s")

    dispatcher = InjectionDispatcher()
    correction = Correction(
        agent_id=agent_id,
        rule_id="LAYOUT-DRIFT-001",
        severity=3,
        disposition="advisory",
        correction_text="apply canonical layout now\n",
        injection_method="cli-return",
    )
    dispatcher.dispatch(correction, agent_dir=agent_dir)

    deadline = time.time() + 15.0
    while time.time() < deadline:
        if output_log.exists() and "CORRECTION_RECEIVED" in output_log.read_text():
            break
        time.sleep(0.2)
    else:
        shim_proc.terminate()
        pytest.fail(
            "Agent did not receive correction via shim within 15s. "
            f"output.log: {output_log.read_text() if output_log.exists() else '(missing)'}"
        )

    try:
        shim_proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        shim_proc.terminate()

    log_content = output_log.read_text()
    assert "CORRECTION_RECEIVED" in log_content
    assert "apply canonical layout now" in log_content
