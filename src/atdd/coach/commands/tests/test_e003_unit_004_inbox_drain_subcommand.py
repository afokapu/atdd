# URN: test:observe-and-correct:E003-UNIT-004-inbox-drain-subcommand
# Acceptance: acc:observe-and-correct:E003-UNIT-004-inbox-drain-subcommand
# WMBT: wmbt:observe-and-correct:E003
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E003-UNIT-004 — `atdd agent inbox drain` reads unconsumed cli-return.jsonl
entries and marks them consumed.

Issue #824.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _write_cli_return(path: Path, text: str) -> None:
    record = {
        "rule_id": "TEST-001",
        "correction_text": text,
        "severity": 3,
        "issued_at": "2026-05-21T00:00:00Z",
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def test_agent_module_exposes_inbox_drain():
    """atdd.coach.commands.agent exposes cmd_inbox_drain."""
    from atdd.coach.commands import agent

    assert hasattr(agent, "cmd_inbox_drain"), (
        "agent module missing cmd_inbox_drain (RED: not implemented yet)"
    )


def test_inbox_drain_returns_unconsumed_entries(tmp_path):
    """cmd_inbox_drain returns new entries and advances the consumed offset."""
    from atdd.coach.commands.agent import cmd_inbox_drain

    agent_id = "inbox-drain-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    _write_cli_return(cli_return_path, "first correction\n")
    _write_cli_return(cli_return_path, "second correction\n")

    entries = cmd_inbox_drain(agent_id=agent_id, runtime_root=tmp_path)
    assert len(entries) == 2, f"Expected 2 entries, got {entries}"
    assert entries[0]["correction_text"] == "first correction\n"
    assert entries[1]["correction_text"] == "second correction\n"


def test_inbox_drain_marks_consumed(tmp_path):
    """A second drain returns no entries."""
    from atdd.coach.commands.agent import cmd_inbox_drain

    agent_id = "inbox-drain-002"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    _write_cli_return(cli_return_path, "only entry\n")

    cmd_inbox_drain(agent_id=agent_id, runtime_root=tmp_path)
    second = cmd_inbox_drain(agent_id=agent_id, runtime_root=tmp_path)

    assert second == [], f"Expected empty second drain, got {second}"


def test_inbox_drain_empty_when_no_entries(tmp_path):
    """drain on an empty (or missing) cli-return.jsonl returns []."""
    from atdd.coach.commands.agent import cmd_inbox_drain

    agent_id = "inbox-drain-empty"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    result = cmd_inbox_drain(agent_id=agent_id, runtime_root=tmp_path)
    assert result == []


def test_inbox_drain_subcommand_registered_in_cli():
    """The 'inbox' subcommand (with drain action) is registered in the CLI parser."""
    from atdd.coach.commands.agent import _build_parser

    parser = _build_parser()
    # Verify inbox subcommand registered — will error if not present
    args = parser.parse_args(["inbox", "drain", "--agent-id", "test-001"])
    assert args.subcommand == "inbox"
    assert args.inbox_action == "drain"
