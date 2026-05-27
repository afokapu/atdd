# URN: test:observe-and-correct:E007-UNIT-003-existing-e003-tests-pass-with-sentinel-disabled
# Acceptance: acc:observe-and-correct:E007-UNIT-003-existing-e003-tests-pass-with-sentinel-disabled
# WMBT: wmbt:observe-and-correct:E007
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E007-UNIT-003 — Pre-existing E003 unit tests that assert exact byte payloads
remain GREEN when PersonaShim is constructed with submit_sentinel=b'' (no-sentinel
mode), confirming the sentinel is additive and does not break existing tests.

Issue #862.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _append_cli_return(path: Path, correction_text: str) -> None:
    record = {
        "rule_id": "TEST-E007-003",
        "correction_text": correction_text,
        "severity": 3,
        "issued_at": "2026-05-26T00:00:00Z",
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def test_e003_drain_scenario_unchanged_with_sentinel_disabled(tmp_path):
    """The E003-UNIT-002 'shim drains cli-return' assertion holds exactly when
    submit_sentinel=b'' — no extra byte is appended, preserving the original
    byte-for-byte contract.

    RED: TypeError — submit_sentinel not yet accepted by PersonaShim.__init__.
    """
    from atdd.coach.shim import PersonaShim

    agent_id = "e007-unit-003-drain"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    captured_writes: list[bytes] = []

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: captured_writes.append(data),
        submit_sentinel=b"",  # disabled — E003 byte-exact behaviour preserved
    )

    _append_cli_return(cli_return_path, "Please commit your changes.\n")

    shim.poll_once()

    assert len(captured_writes) == 1
    assert b"Please commit your changes" in captured_writes[0]
    # No sentinel byte appended when explicitly disabled.
    assert not captured_writes[0].endswith(b"\r"), (
        f"submit_sentinel=b'' must not append \\r; got {captured_writes[0]!r}"
    )
    assert not captured_writes[0].endswith(b"\n\n"), (
        f"submit_sentinel=b'' must not add extra newline; got {captured_writes[0]!r}"
    )


def test_e003_idempotency_scenario_unchanged_with_sentinel_disabled(tmp_path):
    """The E003-UNIT-002 'drains only unconsumed entries' assertion holds when
    submit_sentinel=b'' — one delivery, correct content, no tail bytes.

    RED: TypeError — submit_sentinel not accepted.
    """
    from atdd.coach.shim import PersonaShim

    agent_id = "e007-unit-003-idempotent"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    captured_writes: list[bytes] = []

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: captured_writes.append(data),
        submit_sentinel=b"",
    )

    _append_cli_return(cli_return_path, "First correction\n")
    shim.poll_once()
    shim.poll_once()  # must not re-deliver

    assert len(captured_writes) == 1, (
        f"Expected 1 write (idempotent drain), got {len(captured_writes)}"
    )


def test_e003_two_entries_unchanged_with_sentinel_disabled(tmp_path):
    """The E003 'two sequential entries in order' scenario still holds with
    submit_sentinel=b'' — two writes, correct order, no extra bytes.

    RED: TypeError — submit_sentinel not accepted.
    """
    from atdd.coach.shim import PersonaShim

    agent_id = "e007-unit-003-two"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    captured_writes: list[bytes] = []

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: captured_writes.append(data),
        submit_sentinel=b"",
    )

    _append_cli_return(cli_return_path, "First\n")
    _append_cli_return(cli_return_path, "Second\n")
    shim.poll_once()
    shim.poll_once()

    assert len(captured_writes) == 2
    assert b"First" in captured_writes[0]
    assert b"Second" in captured_writes[1]
    # Neither entry should have a trailing sentinel when disabled.
    for i, w in enumerate(captured_writes):
        assert not w.endswith(b"\r"), (
            f"Entry {i} ends with \\r despite submit_sentinel=b'': {w!r}"
        )
