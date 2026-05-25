# URN: test:observe-and-correct:E003-SMOKE-001-correction-loop-end-to-end
# Acceptance: acc:observe-and-correct:E003-SMOKE-001-correction-loop-end-to-end
# WMBT: wmbt:observe-and-correct:E003
# Phase: SMOKE
# Assertion: behavioral
# Layer: integration
# Scope: COMPONENT SMOKE — atdd-shim CLI wrapping a synthetic agent script.
#
# Routes through the real atdd-shim entry point (python -m atdd.coach.shim)
# so that PersonaShim is exercised via its production CLI surface rather than
# via direct class instantiation.
# The production spawn wiring guarantee (cmd_spawn → PersonaShim) is in:
#   src/atdd/coach/commands/tests/test_e004_smoke_001_real_spawn_uses_shim_process_tree.py
#
# (#841: production wiring. #862: rewritten from direct PersonaShim to real entry point.)
"""E003-SMOKE-001 — Component smoke: PersonaShim correction-loop via atdd-shim CLI.

  synthetic agent script → output.log → InjectionDispatcher writes cli-return.jsonl
  → atdd-shim poll loop delivers bytes to agent stdin → agent acknowledges in output.log.

Exercises the shim through its real CLI entry point (`python -m atdd.coach.shim`),
not via direct class instantiation. Proves the correction loop closes end-to-end.

Issue #824 (component). Scoped by #841 (wiring). #862 (real entry point).
Paired with #825 (close-the-loop SMOKE convention).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.platform]

# Resolve worktree src root so the subprocess uses the local persona_shim.py
# rather than the pipx-installed copy.
_SRC_ROOT = str(Path(__file__).parent.parent.parent.parent.parent)  # …/src

_AGENT_SCRIPT = """
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
    """A synthetic agent emits drift; InjectionDispatcher fires; atdd-shim delivers bytes."""
    from atdd.coach.commands.observer import (
        InjectionDispatcher,
        Correction,
    )

    agent_id = "e2e-loop-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    agent_script = tmp_path / "agent_script.py"
    agent_script.write_text(_AGENT_SCRIPT)

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{_SRC_ROOT}:{existing_pythonpath}" if existing_pythonpath else _SRC_ROOT

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "atdd.coach.shim",
            "--agent-id", agent_id,
            "--runtime-dir", str(tmp_path),
            "--",
            sys.executable, str(agent_script), str(tmp_path), agent_id,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    output_log = agent_dir / "output.log"

    # Wait for the agent to emit the drift trigger (written to output.log by the agent)
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if output_log.exists() and "DRIFT_TRIGGER" in output_log.read_text():
            break
        time.sleep(0.1)
    else:
        proc.terminate()
        pytest.fail("Synthetic agent did not emit DRIFT_TRIGGER in time")

    # Inject a correction via InjectionDispatcher (writes to cli-return.jsonl)
    correction = Correction(
        agent_id=agent_id,
        rule_id="LAYOUT-DRIFT-001",
        severity=3,
        disposition="advisory",
        correction_text="apply canonical layout now\n",
        injection_method="cli-return",
    )
    dispatcher = InjectionDispatcher()
    dispatcher.dispatch(correction, agent_dir=agent_dir)

    # Wait for the shim to deliver the correction and the agent to acknowledge
    deadline = time.time() + 15.0
    while time.time() < deadline:
        if output_log.exists() and "CORRECTION_RECEIVED" in output_log.read_text():
            break
        time.sleep(0.2)
    else:
        proc.terminate()
        pytest.fail(
            "Agent did not receive correction via shim within 15s. "
            f"output.log: {output_log.read_text() if output_log.exists() else '(missing)'}"
        )

    proc.wait(timeout=5.0)
    log_content = output_log.read_text()
    assert "CORRECTION_RECEIVED" in log_content
    assert "apply canonical layout now" in log_content
