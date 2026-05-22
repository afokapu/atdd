# URN: test:observe-and-correct:E003-UNIT-010-shim-fault-isolation
# Acceptance: acc:observe-and-correct:E003-UNIT-010-shim-fault-isolation
# WMBT: wmbt:observe-and-correct:E003
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E003-UNIT-010 — The shim survives a malformed cli-return.jsonl record
without crashing the poll loop; subsequent valid entries are still delivered.

Issue #824.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _write_line(path: Path, line: str) -> None:
    with path.open("a") as f:
        f.write(line + "\n")


def test_shim_skips_invalid_json_line(tmp_path):
    """An invalid JSON line is skipped; the shim does not crash."""
    from atdd.coach.shim import PersonaShim

    agent_id = "fault-iso-001"
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

    # Write a bad JSON line followed by a valid record
    _write_line(cli_return_path, "NOT_VALID_JSON{{{")
    _write_line(cli_return_path, json.dumps({
        "rule_id": "TEST-001",
        "correction_text": "valid correction\n",
        "severity": 3,
        "issued_at": "2026-05-21T00:00:00Z",
    }))

    shim.poll_once()  # consume bad line (skip) + valid record

    assert len(captured_writes) == 1, (
        f"Expected 1 delivery (bad line skipped), got {len(captured_writes)}"
    )
    assert b"valid correction" in captured_writes[0]


def test_shim_skips_record_with_missing_correction_text(tmp_path):
    """A record missing correction_text is skipped without crashing."""
    from atdd.coach.shim import PersonaShim

    agent_id = "fault-iso-002"
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

    # Bad record: missing correction_text
    _write_line(cli_return_path, json.dumps({"rule_id": "TEST-001", "severity": 3}))
    # Good record
    _write_line(cli_return_path, json.dumps({
        "rule_id": "TEST-002",
        "correction_text": "good correction\n",
        "severity": 3,
        "issued_at": "2026-05-21T00:00:00Z",
    }))

    shim.poll_once()

    assert len(captured_writes) == 1
    assert b"good correction" in captured_writes[0]


def test_shim_continues_polling_after_bad_record(tmp_path):
    """After a bad record, subsequent poll cycles still deliver new entries."""
    from atdd.coach.shim import PersonaShim

    agent_id = "fault-iso-003"
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

    _write_line(cli_return_path, "INVALID")
    shim.poll_once()  # bad record — no delivery

    _write_line(cli_return_path, json.dumps({
        "rule_id": "TEST-003",
        "correction_text": "after bad\n",
        "severity": 3,
        "issued_at": "2026-05-21T00:00:00Z",
    }))
    shim.poll_once()  # new valid record

    assert len(captured_writes) == 1
    assert b"after bad" in captured_writes[0]
