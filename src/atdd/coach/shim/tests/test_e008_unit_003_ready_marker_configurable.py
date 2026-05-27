# URN: test:observe-and-correct:E008-UNIT-003-ready-marker-configurable
# Acceptance: acc:observe-and-correct:E008-UNIT-003-ready-marker-configurable
# WMBT: wmbt:observe-and-correct:E008
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E008-UNIT-003 — The TUI ready-marker pattern is configurable via
ATDD_SHIM_READY_MARKER (default: ❯); the shim scans the tail of output.log
for the marker byte string.

Issue #862.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _append_cli_return(path: Path, correction_text: str) -> None:
    record = {
        "rule_id": "TEST-E008-003",
        "correction_text": correction_text,
        "severity": 3,
        "issued_at": "2026-05-26T00:00:00Z",
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def test_ready_marker_configurable_blocks_until_custom_marker(tmp_path, monkeypatch):
    """poll_once() must not be called until the custom ATDD_SHIM_READY_MARKER
    string appears in output.log; the default '❯' must NOT trigger the gate
    when a different marker is configured.

    RED: fails because _run_loop ignores ATDD_SHIM_READY_MARKER and calls
    poll_once() immediately.
    """
    from atdd.coach.shim import PersonaShim

    custom_marker = "READY_SENTINEL"
    agent_id = "e006-unit-003"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    output_log = agent_dir / "output.log"
    cli_return_path = agent_dir / "cli-return.jsonl"

    monkeypatch.setenv("ATDD_SHIM_READY_MARKER", custom_marker)
    monkeypatch.setenv("ATDD_SHIM_BOOTSTRAP_DELAY_S", "10.0")

    _append_cli_return(cli_return_path, "MARKER_TEST_PAYLOAD\n")

    poll_call_times: list[float] = []
    start = time.monotonic()

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "1.0"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: None,
    )

    original_poll = shim.poll_once

    def tracked_poll() -> None:
        poll_call_times.append(time.monotonic() - start)
        original_poll()

    monkeypatch.setattr(shim, "poll_once", tracked_poll)

    # Write the custom marker to output.log after 0.3 s.
    def write_custom_marker() -> None:
        time.sleep(0.3)
        output_log.write_bytes(custom_marker.encode())

    t = threading.Thread(target=write_custom_marker, daemon=True)
    t.start()

    shim.run(timeout=2.0)

    assert poll_call_times, "poll_once was never called during _run_loop"
    first_call = poll_call_times[0]
    assert first_call >= 0.25, (
        f"poll_once called at {first_call:.3f}s — before the custom marker "
        f"'{custom_marker}' at 0.3s; ATDD_SHIM_READY_MARKER must be honoured"
    )


def test_default_marker_does_not_fire_with_custom_marker_set(tmp_path, monkeypatch):
    """When ATDD_SHIM_READY_MARKER is 'CUSTOM_GATE', the default '❯' glyph
    written to output.log must NOT release the gate prematurely.

    RED: fails because the gate does not exist; poll_once fires early.
    """
    from atdd.coach.shim import PersonaShim

    custom_marker = "CUSTOM_GATE"
    agent_id = "e006-unit-003b"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    output_log = agent_dir / "output.log"

    monkeypatch.setenv("ATDD_SHIM_READY_MARKER", custom_marker)
    monkeypatch.setenv("ATDD_SHIM_BOOTSTRAP_DELAY_S", "10.0")

    poll_call_times: list[float] = []
    start = time.monotonic()

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "1.0"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: None,
    )

    original_poll = shim.poll_once

    def tracked_poll() -> None:
        poll_call_times.append(time.monotonic() - start)
        original_poll()

    monkeypatch.setattr(shim, "poll_once", tracked_poll)

    # Write the DEFAULT marker (❯) — must NOT release the CUSTOM_GATE gate.
    def write_default_marker() -> None:
        time.sleep(0.15)
        # Append default marker — this must NOT release the gate
        with output_log.open("ab") as f:
            f.write("❯".encode())

    # Write the custom marker later at 0.5s
    def write_custom_marker() -> None:
        time.sleep(0.5)
        with output_log.open("ab") as f:
            f.write(custom_marker.encode())

    for target in (write_default_marker, write_custom_marker):
        threading.Thread(target=target, daemon=True).start()

    shim.run(timeout=2.0)

    assert poll_call_times, "poll_once was never called"
    first_call = poll_call_times[0]
    assert first_call >= 0.4, (
        f"poll_once called at {first_call:.3f}s; the default '❯' marker at 0.15s "
        f"must not release the gate when ATDD_SHIM_READY_MARKER='CUSTOM_GATE'; "
        f"expected first call >= 0.4s (custom marker at 0.5s)"
    )
