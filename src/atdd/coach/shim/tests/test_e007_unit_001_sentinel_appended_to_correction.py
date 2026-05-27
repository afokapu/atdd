# URN: test:observe-and-correct:E007-UNIT-001-sentinel-appended-to-correction
# Acceptance: acc:observe-and-correct:E007-UNIT-001-sentinel-appended-to-correction
# WMBT: wmbt:observe-and-correct:E007
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E007-UNIT-001 — _process_cli_return_line appends the submit sentinel (\\r by
default for claude-code) to correction_text before writing to the pty; the
pty_write_sink receives correction_text + sentinel.

Issue #862.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _append_cli_return(path: Path, correction_text: str) -> None:
    record = {
        "rule_id": "TEST-E007-001",
        "correction_text": correction_text,
        "severity": 3,
        "issued_at": "2026-05-26T00:00:00Z",
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def test_sentinel_appended_to_correction(tmp_path):
    """poll_once() must deliver correction_text + sentinel (b'\\r') to the sink.

    RED: fails with TypeError because PersonaShim.__init__ does not yet accept
    the submit_sentinel keyword argument.
    """
    from atdd.coach.shim import PersonaShim

    agent_id = "e007-unit-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    captured_writes: list[bytes] = []

    # submit_sentinel is the new parameter introduced by E007 — TypeError in RED.
    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: captured_writes.append(data),
        submit_sentinel=b"\r",
    )

    _append_cli_return(cli_return_path, "hello world")

    shim.poll_once()

    assert len(captured_writes) == 1, (
        f"Expected 1 write but got {len(captured_writes)}"
    )
    assert captured_writes[0] == b"hello world\r", (
        f"Expected b'hello world\\r' but got {captured_writes[0]!r}; "
        f"_process_cli_return_line must append the submit_sentinel"
    )


def test_sentinel_appears_exactly_once_at_end(tmp_path):
    """The sentinel byte appears exactly once, at the end of the payload;
    the original correction_text is not modified in cli-return.jsonl.

    RED: TypeError — submit_sentinel parameter not accepted.
    """
    from atdd.coach.shim import PersonaShim

    agent_id = "e007-unit-001b"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    captured_writes: list[bytes] = []

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: captured_writes.append(data),
        submit_sentinel=b"\r",
    )

    _append_cli_return(cli_return_path, "hello world")

    shim.poll_once()

    assert captured_writes, "No write reached the pty_write_sink"
    payload = captured_writes[0]
    assert payload.endswith(b"\r"), (
        f"Expected payload to end with b'\\r' but got {payload!r}"
    )
    # Sentinel must appear exactly once at the end, not embedded in the text.
    cr_positions = [i for i, b in enumerate(payload) if b == 0x0D]
    assert len(cr_positions) == 1 and cr_positions[0] == len(payload) - 1, (
        f"Expected exactly one \\r at the end; positions found: {cr_positions} "
        f"in payload {payload!r}"
    )
    # cli-return.jsonl must still contain the original text (no sentinel on disk).
    raw = cli_return_path.read_text()
    assert "\r" not in raw, (
        f"cli-return.jsonl must not contain the sentinel byte; content: {raw!r}"
    )
