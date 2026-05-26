# URN: test:observe-and-correct:E008-SMOKE-001-delivery-waits-for-tui
# Acceptance: acc:observe-and-correct:E008-SMOKE-001-delivery-waits-for-tui
# WMBT: wmbt:observe-and-correct:E008
# Phase: SMOKE
# Assertion: behavioral
# Layer: integration
# Scope: COMPONENT SMOKE — atdd-shim CLI wrapping a synthetic slow-start agent.
#
# The synthetic agent immediately reads stdin (non-blocking), so any early
# delivery is visible at check-time. Without the wait-for-ready gate the shim
# delivers the correction within ~0.1s (before the 0.5s early-check), making
# the "RECV: NOT present at 0.5s" assertion fail.
"""E008-SMOKE-001 — With a synthetic slow-start agent, cli-return.jsonl entries
are not delivered to the agent's stdin until after the ready-marker appears in
output.log.

The synthetic agent:
  1. Immediately reads stdin in a non-blocking loop (detects early deliveries).
  2. After 1.0s, writes the ready-marker to stdout (teed to output.log by shim).
  3. Echoes any received stdin bytes as RECV:<text> to output.log.

Without the E008 gate: shim delivers correction at ~0.1s → agent reads at
~0.1s → RECV:WAIT_GATE_TEST appears by 0.5s → assertion FAILS (RED).

With the gate: shim waits for marker (at 1s) → delivery after marker → RECV:
does NOT appear before 0.5s → GREEN.

Issue #862.
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

_SRC_ROOT = str(Path(__file__).parent.parent.parent.parent.parent)  # …/src

_READY_MARKER = "TUI_IS_READY"

# The synthetic agent reads stdin non-blocking the whole time.
# After 1s it writes the ready-marker to stdout (shim tees to output.log).
# Any stdin bytes received are echoed as RECV:<text> to output.log.
_SLOW_START_AGENT = r"""
import sys, os, time, select

runtime_dir = sys.argv[1]
agent_id   = sys.argv[2]
agent_dir  = os.path.join(runtime_dir, "agents", agent_id)
output_log = os.path.join(agent_dir, "output.log")
os.makedirs(agent_dir, exist_ok=True)

READY_MARKER = os.environ.get("ATDD_SHIM_READY_MARKER", "TUI_IS_READY")
start        = time.time()
marker_written = False
stdin_fd = sys.stdin.fileno()

deadline = time.time() + 8.0
while time.time() < deadline:
    # Write the ready-marker to stdout exactly once at 1s (shim tees to output.log).
    if not marker_written and time.time() - start >= 1.0:
        sys.stdout.write(READY_MARKER)
        sys.stdout.flush()
        marker_written = True

    # Non-blocking stdin read.
    r, _, _ = select.select([stdin_fd], [], [], 0.05)
    if r:
        try:
            chunk = os.read(stdin_fd, 4096)
        except OSError:
            break
        if chunk:
            text = chunk.decode("utf-8", errors="replace")
            # Strip only the \r sentinel if present (don't strip \n in correction_text)
            text = text.rstrip("\r")
            with open(output_log, "a") as f:
                f.write("RECV:" + text + "\n")
            # Exit after first delivery so the test can assert timing.
            break

sys.exit(0)
"""


def _append_cli_return(path: Path, correction_text: str) -> None:
    record = {
        "rule_id": "TEST-E008-SMOKE-001",
        "correction_text": correction_text,
        "severity": 3,
        "issued_at": "2026-05-26T00:00:00Z",
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def test_delivery_waits_for_tui_ready_marker(tmp_path):
    """output.log must NOT contain 'RECV:WAIT_GATE_TEST' within the first 0.5s;
    it MUST appear after the ready-marker at ~1.0s.

    RED: without the gate the shim delivers immediately (~0.1s); the agent
    reads the bytes early and writes RECV: before 0.5s — assertion fails.
    """
    agent_id = "e006-smoke-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    output_log = agent_dir / "output.log"
    cli_return_path = agent_dir / "cli-return.jsonl"

    _append_cli_return(cli_return_path, "WAIT_GATE_TEST")

    agent_script = tmp_path / "slow_start_agent.py"
    agent_script.write_text(_SLOW_START_AGENT)

    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{_SRC_ROOT}:{existing_pp}" if existing_pp else _SRC_ROOT
    env["ATDD_SHIM_READY_MARKER"] = _READY_MARKER
    env["ATDD_SHIM_BOOTSTRAP_DELAY_S"] = "5.0"  # delay >> marker; gate must use marker

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

    try:
        # ── Early check (0.5 s) ─────────────────────────────────────────
        time.sleep(0.5)
        early_content = output_log.read_text() if output_log.exists() else ""
        assert "RECV:WAIT_GATE_TEST" not in early_content, (
            "Correction was delivered BEFORE the TUI ready-marker appeared "
            f"(gate must hold delivery until marker seen). "
            f"output.log at 0.5s: {early_content!r}"
        )

        # ── Post-marker check (up to 8 s total) ─────────────────────────
        deadline = time.time() + 7.0
        while time.time() < deadline:
            content = output_log.read_text() if output_log.exists() else ""
            if "RECV:WAIT_GATE_TEST" in content:
                break
            time.sleep(0.2)
        else:
            proc.terminate()
            content = output_log.read_text() if output_log.exists() else ""
            pytest.fail(
                "Correction was never delivered after the TUI ready-marker appeared. "
                f"output.log: {content!r}"
            )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()
