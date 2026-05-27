# URN: test:observe-and-correct:E008-UNIT-002-bootstrap-delay-fallback
# Acceptance: acc:observe-and-correct:E008-UNIT-002-bootstrap-delay-fallback
# WMBT: wmbt:observe-and-correct:E008
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E008-UNIT-002 — When the TUI ready-marker never appears in output.log, the
shim falls back to starting cli-return delivery after ATDD_SHIM_BOOTSTRAP_DELAY_S
seconds have elapsed since process spawn.

Issue #862.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _append_cli_return(path: Path, correction_text: str) -> None:
    record = {
        "rule_id": "TEST-E008-002",
        "correction_text": correction_text,
        "severity": 3,
        "issued_at": "2026-05-26T00:00:00Z",
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def test_bootstrap_delay_fallback_blocks_poll(tmp_path, monkeypatch):
    """When output.log never receives the ready-marker, poll_once() must not
    be called before ATDD_SHIM_BOOTSTRAP_DELAY_S seconds elapse.

    RED: fails because _run_loop currently ignores ATDD_SHIM_BOOTSTRAP_DELAY_S
    and calls poll_once() immediately.
    """
    from atdd.coach.shim import PersonaShim

    agent_id = "e006-unit-002"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    # Delay of 0.4s; output.log stays empty — marker never appears.
    monkeypatch.setenv("ATDD_SHIM_BOOTSTRAP_DELAY_S", "0.4")
    monkeypatch.setenv("ATDD_SHIM_READY_MARKER", "❯")

    _append_cli_return(cli_return_path, "DELAY_FALLBACK_TEST\n")

    poll_call_times: list[float] = []
    delivery_times: list[float] = []
    start = time.monotonic()

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "1.0"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: delivery_times.append(time.monotonic() - start),
    )

    original_poll = shim.poll_once

    def tracked_poll() -> None:
        poll_call_times.append(time.monotonic() - start)
        original_poll()

    monkeypatch.setattr(shim, "poll_once", tracked_poll)

    # Output log intentionally left empty — no ready-marker ever written.
    shim.run(timeout=2.0)

    assert poll_call_times, "poll_once was never called during _run_loop"
    first_call = poll_call_times[0]
    assert first_call >= 0.3, (
        f"poll_once called at {first_call:.3f}s which is before the "
        f"ATDD_SHIM_BOOTSTRAP_DELAY_S=0.4s fallback; the shim must wait "
        f"the full delay when the ready-marker never appears"
    )


def test_bootstrap_delay_fallback_delivers_entry(tmp_path, monkeypatch):
    """After the bootstrap delay elapses, the pre-seeded cli-return entry IS
    delivered — confirming the fallback unblocks delivery.

    RED: fails because the gate logic does not exist; poll_once fires before delay.
    """
    from atdd.coach.shim import PersonaShim

    agent_id = "e006-unit-002b"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    monkeypatch.setenv("ATDD_SHIM_BOOTSTRAP_DELAY_S", "0.4")
    monkeypatch.setenv("ATDD_SHIM_READY_MARKER", "❯")

    _append_cli_return(cli_return_path, "AFTER_DELAY_PAYLOAD\n")

    delivery_times: list[float] = []
    captured_writes: list[bytes] = []
    start = time.monotonic()

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "1.0"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: (
            delivery_times.append(time.monotonic() - start),
            captured_writes.append(data),
        ),
    )

    shim.run(timeout=2.0)

    # Entry must be delivered, but not before the delay.
    assert captured_writes, "cli-return entry was never delivered after bootstrap delay"
    early = [t for t in delivery_times if t < 0.3]
    assert not early, (
        f"Entry delivered before ATDD_SHIM_BOOTSTRAP_DELAY_S=0.4s at: {early}; "
        f"no-crash guarantee also required — the shim must not hang when marker absent"
    )


def test_no_crash_when_ready_marker_never_appears(tmp_path, monkeypatch):
    """_run_loop must complete without exception even if the ready-marker never
    appears in output.log.

    RED: currently does not crash, but this test also asserts timing constraint
    via the delay gate (so it fails because no gate exists).
    """
    from atdd.coach.shim import PersonaShim

    agent_id = "e006-unit-002c"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    monkeypatch.setenv("ATDD_SHIM_BOOTSTRAP_DELAY_S", "0.4")
    monkeypatch.setenv("ATDD_SHIM_READY_MARKER", "❯")

    poll_call_times: list[float] = []
    start = time.monotonic()

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "0.8"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: None,
    )

    original_poll = shim.poll_once

    def tracked_poll() -> None:
        poll_call_times.append(time.monotonic() - start)
        original_poll()

    monkeypatch.setattr(shim, "poll_once", tracked_poll)

    # Must not raise
    exit_code = shim.run(timeout=3.0)

    assert poll_call_times, "poll_once was never called"
    assert poll_call_times[0] >= 0.3, (
        f"First poll_once at {poll_call_times[0]:.3f}s — expected >= 0.3s "
        f"(ATDD_SHIM_BOOTSTRAP_DELAY_S=0.4); gate logic missing"
    )
