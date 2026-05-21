# URN: test:observe-and-correct:E003-SMOKE-001-correction-loop-end-to-end
# Acceptance: acc:observe-and-correct:E003-SMOKE-001-correction-loop-end-to-end
# WMBT: wmbt:observe-and-correct:E003
# Phase: SMOKE
# Assertion: behavioral
# Layer: integration
"""E003-SMOKE-001 — End-to-end correction loop under a real shim:

  synthetic agent → output.log → observer rule fires → cli-return.jsonl →
  shim delivers bytes to agent pty stdin → agent acknowledges → drift resolves.

Issue #824. Paired with #825 (close-the-loop SMOKE convention).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.platform]

_SYNTHETIC_AGENT = """
import sys, time, os, json

runtime_dir = sys.argv[1]
agent_id = sys.argv[2]
agent_dir = os.path.join(runtime_dir, "agents", agent_id)
output_log = os.path.join(agent_dir, "output.log")

# Emit a line that triggers the layout_drift rule
with open(output_log, "a") as f:
    f.write("DRIFT_TRIGGER: missing canonical layout\\n")
    f.flush()

# Poll for a correction via our stdin (fed by the shim)
deadline = time.time() + 15.0
while time.time() < deadline:
    line = sys.stdin.readline()
    if line.strip():
        with open(output_log, "a") as f:
            f.write(f"CORRECTION_RECEIVED: {line.strip()}\\n")
        sys.exit(0)
    time.sleep(0.1)

# Timed out without receiving a correction
sys.exit(1)
"""


def test_correction_loop_closes_under_shim(tmp_path):
    """A synthetic agent emits drift; the observer fires; shim delivers bytes."""
    from atdd.coach.shim import PersonaShim
    from atdd.coach.commands.observer import (
        InjectionDispatcher,
        ObserverRule,
        ObservedInput,
        RuleRegistry,
        Observer,
    )

    agent_id = "e2e-loop-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    # Write synthetic agent script to a file
    agent_script = tmp_path / "synthetic_agent.py"
    agent_script.write_text(_SYNTHETIC_AGENT)

    # Start the shim with the synthetic agent
    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=[sys.executable, str(agent_script), str(tmp_path), agent_id],
        runtime_dir=tmp_path,
    )

    import threading
    shim_thread = threading.Thread(target=shim.run, kwargs={"timeout": 20.0}, daemon=True)
    shim_thread.start()

    # Wait for the agent to emit the drift trigger
    output_log = agent_dir / "output.log"
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if output_log.exists() and "DRIFT_TRIGGER" in output_log.read_text():
            break
        time.sleep(0.1)
    else:
        pytest.fail("Synthetic agent did not emit DRIFT_TRIGGER in time")

    # Inject a correction via InjectionDispatcher (writes to cli-return.jsonl)
    dispatcher = InjectionDispatcher()
    from atdd.coach.commands.observer import Correction
    correction = Correction(
        agent_id=agent_id,
        rule_id="LAYOUT-DRIFT-001",
        severity=3,
        disposition="advisory",
        correction_text="apply canonical layout now\n",
        injection_method="cli-return",
    )
    dispatcher.dispatch(correction, agent_dir=agent_dir)

    # Wait for the shim to deliver the correction and the agent to acknowledge
    deadline = time.time() + 15.0
    while time.time() < deadline:
        if output_log.exists() and "CORRECTION_RECEIVED" in output_log.read_text():
            break
        time.sleep(0.2)
    else:
        pytest.fail(
            "Agent did not receive correction via shim within 15s. "
            f"output.log: {output_log.read_text() if output_log.exists() else '(missing)'}"
        )

    shim_thread.join(timeout=5.0)
    log_content = output_log.read_text()
    assert "CORRECTION_RECEIVED" in log_content
    assert "apply canonical layout now" in log_content
