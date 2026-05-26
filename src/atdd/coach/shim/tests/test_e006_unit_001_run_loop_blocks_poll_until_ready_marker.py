# URN: test:observe-and-correct:E006-UNIT-001-run-loop-blocks-poll-until-ready-marker
# Acceptance: acc:observe-and-correct:E006-UNIT-001-run-loop-blocks-poll-until-ready-marker
# WMBT: wmbt:observe-and-correct:E006
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E006-UNIT-001 — _run_loop does not call poll_once() until the TUI ready-marker
appears in output.log; once the marker appears, subsequent cli-return.jsonl entries
are delivered normally.

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
        "rule_id": "TEST-E006-001",
        "correction_text": correction_text,
        "severity": 3,
        "issued_at": "2026-05-26T00:00:00Z",
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def test_run_loop_blocks_poll_until_ready_marker(tmp_path, monkeypatch):
    """poll_once() must not be called before the TUI ready-marker appears in
    output.log; once the marker appears at ~0.3s the pre-seeded cli-return
    entry must be delivered to the pty_write_sink.

    RED: fails because _run_loop currently calls poll_once() on every
    iteration (~0.1s) without checking for the ready-marker.
    """
    from atdd.coach.shim import PersonaShim

    agent_id = "e006-unit-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    output_log = agent_dir / "output.log"
    cli_return_path = agent_dir / "cli-return.jsonl"

    monkeypatch.setenv("ATDD_SHIM_BOOTSTRAP_DELAY_S", "5.0")
    monkeypatch.setenv("ATDD_SHIM_READY_MARKER", "❯")  # ❯

    # Pre-seed cli-return entry before the shim starts
    _append_cli_return(cli_return_path, "GATE_TEST_PAYLOAD\n")

    captured_writes: list[tuple[float, bytes]] = []
    poll_call_times: list[float] = []
    start = time.monotonic()

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "1.0"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: captured_writes.append(
            (time.monotonic() - start, data)
        ),
    )

    # Patch poll_once to record timestamps while preserving original behaviour.
    original_poll = shim.poll_once

    def tracked_poll() -> None:
        poll_call_times.append(time.monotonic() - start)
        original_poll()

    monkeypatch.setattr(shim, "poll_once", tracked_poll)

    # Write the ready-marker to output.log after 0.3 s — simulates a slow TUI.
    def write_marker() -> None:
        time.sleep(0.3)
        output_log.write_bytes("❯".encode())

    t = threading.Thread(target=write_marker, daemon=True)
    t.start()

    shim.run(timeout=2.0)

    assert poll_call_times, "poll_once was never called during _run_loop"
    first_call = poll_call_times[0]
    assert first_call >= 0.25, (
        f"poll_once called at {first_call:.3f}s — before the ready-marker at 0.3s; "
        f"_run_loop must block poll_once() until the marker appears in output.log"
    )
    assert captured_writes, (
        "cli-return entry was never delivered after the ready-marker appeared"
    )
    delivered_bytes = b"".join(data for _, data in captured_writes)
    assert b"GATE_TEST_PAYLOAD" in delivered_bytes


def test_run_loop_no_delivery_before_marker(tmp_path, monkeypatch):
    """No delivery must occur before the ready-marker appears even when multiple
    poll_once calls would normally happen during the marker-wait window.

    RED: fails because current code delivers immediately on the first iteration.
    """
    from atdd.coach.shim import PersonaShim

    agent_id = "e006-unit-001b"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    output_log = agent_dir / "output.log"
    cli_return_path = agent_dir / "cli-return.jsonl"

    monkeypatch.setenv("ATDD_SHIM_BOOTSTRAP_DELAY_S", "5.0")
    monkeypatch.setenv("ATDD_SHIM_READY_MARKER", "❯")

    _append_cli_return(cli_return_path, "MUST_NOT_DELIVER_EARLY\n")

    delivery_times: list[float] = []
    start = time.monotonic()

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "1.0"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: delivery_times.append(time.monotonic() - start),
    )

    # Marker appears at 0.4 s
    def write_marker() -> None:
        time.sleep(0.4)
        output_log.write_bytes("❯".encode())

    t = threading.Thread(target=write_marker, daemon=True)
    t.start()

    shim.run(timeout=2.0)

    early_deliveries = [t for t in delivery_times if t < 0.3]
    assert not early_deliveries, (
        f"Delivery occurred before the ready-marker at times: {early_deliveries}; "
        f"_run_loop must not call poll_once() until the marker appears in output.log"
    )
