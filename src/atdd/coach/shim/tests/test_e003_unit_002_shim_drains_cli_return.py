# URN: test:observe-and-correct:E003-UNIT-002-shim-drains-cli-return
# Acceptance: acc:observe-and-correct:E003-UNIT-002-shim-drains-cli-return
# WMBT: wmbt:observe-and-correct:E003
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E003-UNIT-002 — The shim polls cli-return.jsonl for new entries and writes
the correction_text bytes to the pty master fd.

Issue #824.
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
        "rule_id": "TEST-RULE-001",
        "correction_text": correction_text,
        "severity": 3,
        "issued_at": "2026-05-21T00:00:00Z",
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def test_shim_module_exposes_persona_shim():
    from atdd.coach.shim import PersonaShim  # noqa: F401


def test_shim_drains_cli_return_entry(tmp_path):
    """A new cli-return.jsonl entry is detected and correction_text is captured.

    Uses a fake pty sink (bytes captured to a list) rather than a real fd.
    """
    from atdd.coach.shim import PersonaShim

    agent_id = "drain-test-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    captured_writes: list[bytes] = []

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: captured_writes.append(data),
    )

    # Pre-seed one entry before the shim starts polling
    _append_cli_return(cli_return_path, "Please commit your changes.\n")

    # Run a single poll cycle
    shim.poll_once()

    assert len(captured_writes) == 1
    assert b"Please commit your changes" in captured_writes[0]


def test_shim_drains_only_unconsumed_entries(tmp_path):
    """After draining entry N, a second poll does not re-deliver it."""
    from atdd.coach.shim import PersonaShim

    agent_id = "drain-idempotent-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    captured_writes: list[bytes] = []

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: captured_writes.append(data),
    )

    _append_cli_return(cli_return_path, "First correction\n")
    shim.poll_once()  # consumes the entry
    shim.poll_once()  # should not re-deliver

    assert len(captured_writes) == 1, f"Expected 1 write, got {len(captured_writes)}"


def test_shim_delivers_second_entry_after_first(tmp_path):
    """Two sequential entries are delivered in order."""
    from atdd.coach.shim import PersonaShim

    agent_id = "drain-two-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    captured_writes: list[bytes] = []

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: captured_writes.append(data),
    )

    _append_cli_return(cli_return_path, "First\n")
    _append_cli_return(cli_return_path, "Second\n")
    shim.poll_once()
    shim.poll_once()

    assert len(captured_writes) == 2
    assert b"First" in captured_writes[0]
    assert b"Second" in captured_writes[1]
