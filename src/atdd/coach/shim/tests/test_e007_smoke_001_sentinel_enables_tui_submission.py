# URN: test:observe-and-correct:E007-SMOKE-001-sentinel-enables-tui-submission
# Acceptance: acc:observe-and-correct:E007-SMOKE-001-sentinel-enables-tui-submission
# WMBT: wmbt:observe-and-correct:E007
# Phase: SMOKE
# Assertion: behavioral
# Layer: integration
# Scope: COMPONENT SMOKE — atdd-shim CLI wrapping a synthetic echo-on-enter agent.
#
# The synthetic agent reads stdin in raw byte mode. It only emits ECHO:<text>
# to output.log when a carriage return (0x0D) is received, buffering otherwise.
# Without the sentinel, the CR never arrives; with ATDD_SHIM_SUBMIT_SENTINEL=\\r,
# it arrives and triggers the echo.
"""E007-SMOKE-001 — A synthetic 'echo-on-enter' agent echoes received lines
prefixed with ECHO: only when a carriage return is received.

With ATDD_SHIM_SUBMIT_SENTINEL=\\r the correction is echoed; without it the
echo does not appear, demonstrating the sentinel is required.

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

_ECHO_ON_ENTER_AGENT = r"""
import sys, os, time, select, tty, termios

runtime_dir = sys.argv[1]
agent_id   = sys.argv[2]
agent_dir  = os.path.join(runtime_dir, "agents", agent_id)
output_log = os.path.join(agent_dir, "output.log")
os.makedirs(agent_dir, exist_ok=True)

READY_MARKER = os.environ.get("ATDD_SHIM_READY_MARKER", "TUI_IS_READY")

# Write the ready-marker immediately so the gate releases at once.
sys.stdout.write(READY_MARKER)
sys.stdout.flush()

fd = sys.stdin.fileno()
old_settings = termios.tcgetattr(fd)
buffer = b""
try:
    tty.setraw(fd)
    deadline = time.time() + 10.0
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            try:
                byte = os.read(fd, 1)
            except OSError:
                break
            if byte == b"\r":
                # Carriage-return received — submit the buffered input.
                text = buffer.decode("utf-8", errors="replace")
                with open(output_log, "a") as f:
                    f.write("ECHO:" + text + "\n")
                buffer = b""
                break  # exit after first submission
            elif byte:
                buffer += byte
finally:
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        pass

sys.exit(0)
"""

_ECHO_ON_ENTER_AGENT_NO_SENTINEL_CHECK = r"""
import sys, os, time, select, tty, termios

runtime_dir = sys.argv[1]
agent_id   = sys.argv[2]
agent_dir  = os.path.join(runtime_dir, "agents", agent_id)
output_log = os.path.join(agent_dir, "output.log")
os.makedirs(agent_dir, exist_ok=True)

READY_MARKER = os.environ.get("ATDD_SHIM_READY_MARKER", "TUI_IS_READY")
sys.stdout.write(READY_MARKER)
sys.stdout.flush()

fd = sys.stdin.fileno()
old_settings = termios.tcgetattr(fd)
buffer = b""
try:
    tty.setraw(fd)
    deadline = time.time() + 3.0
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            try:
                byte = os.read(fd, 1)
            except OSError:
                break
            if byte == b"\r":
                text = buffer.decode("utf-8", errors="replace")
                with open(output_log, "a") as f:
                    f.write("ECHO:" + text + "\n")
                buffer = b""
                break
            elif byte:
                buffer += byte
finally:
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        pass

sys.exit(0)
"""


def _append_cli_return(path: Path, correction_text: str) -> None:
    record = {
        "rule_id": "TEST-E007-SMOKE-001",
        "correction_text": correction_text,
        "severity": 3,
        "issued_at": "2026-05-26T00:00:00Z",
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def _build_env(extra: dict | None = None) -> dict:
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{_SRC_ROOT}:{existing_pp}" if existing_pp else _SRC_ROOT
    env["ATDD_SHIM_READY_MARKER"] = "TUI_IS_READY"
    env["ATDD_SHIM_BOOTSTRAP_DELAY_S"] = "0.5"
    if extra:
        env.update(extra)
    return env


def test_sentinel_enables_tui_submission(tmp_path):
    """With ATDD_SHIM_SUBMIT_SENTINEL='\\r' the echo-on-enter agent echoes the
    correction; ECHO:SUBMIT_SENTINEL_TEST must appear in output.log within 5s.

    RED: ATDD_SHIM_SUBMIT_SENTINEL is not read by the shim; correction bytes
    arrive without \\r; agent never echoes; test times out → FAILS.
    """
    agent_id = "e007-smoke-001-with"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    output_log = agent_dir / "output.log"
    cli_return_path = agent_dir / "cli-return.jsonl"

    _append_cli_return(cli_return_path, "SUBMIT_SENTINEL_TEST")

    agent_script = tmp_path / "echo_on_enter.py"
    agent_script.write_text(_ECHO_ON_ENTER_AGENT)

    env = _build_env({"ATDD_SHIM_SUBMIT_SENTINEL": "\r"})

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
        deadline = time.time() + 8.0
        while time.time() < deadline:
            content = output_log.read_text() if output_log.exists() else ""
            if "ECHO:SUBMIT_SENTINEL_TEST" in content:
                break
            time.sleep(0.2)
        else:
            proc.terminate()
            content = output_log.read_text() if output_log.exists() else ""
            pytest.fail(
                "ECHO:SUBMIT_SENTINEL_TEST did not appear in output.log within 8s; "
                "ATDD_SHIM_SUBMIT_SENTINEL='\\r' must cause the shim to append \\r "
                f"so the echo-on-enter agent submits. output.log: {content!r}"
            )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_without_sentinel_no_echo(tmp_path):
    """Without a submit sentinel the agent buffers input but never receives \\r
    and must NOT emit any ECHO: line within 3s.

    This is the negative control: it PASSES in RED (no sentinel → no echo is
    expected behaviour without the feature) and continues to pass in GREEN
    when sentinel=b'' explicitly disables it.
    """
    agent_id = "e007-smoke-001-without"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    output_log = agent_dir / "output.log"
    cli_return_path = agent_dir / "cli-return.jsonl"

    _append_cli_return(cli_return_path, "SUBMIT_SENTINEL_TEST")

    agent_script = tmp_path / "echo_on_enter_nosent.py"
    agent_script.write_text(_ECHO_ON_ENTER_AGENT_NO_SENTINEL_CHECK)

    # No ATDD_SHIM_SUBMIT_SENTINEL set → no CR appended by shim.
    env = _build_env()
    if "ATDD_SHIM_SUBMIT_SENTINEL" in env:
        del env["ATDD_SHIM_SUBMIT_SENTINEL"]

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
        time.sleep(3.5)
        content = output_log.read_text() if output_log.exists() else ""
        assert "ECHO:" not in content, (
            "Unexpected ECHO: found without a submit sentinel; "
            f"output.log: {content!r}"
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()
