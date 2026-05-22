# URN: test:observe-and-correct:E003-UNIT-005-inbox-peek-subcommand
# Acceptance: acc:observe-and-correct:E003-UNIT-005-inbox-peek-subcommand
# WMBT: wmbt:observe-and-correct:E003
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E003-UNIT-005 — `atdd agent inbox peek` reads unconsumed entries without
advancing the consumed offset.

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


def test_agent_module_exposes_inbox_peek():
    """atdd.coach.commands.agent exposes cmd_inbox_peek."""
    from atdd.coach.commands import agent

    assert hasattr(agent, "cmd_inbox_peek"), (
        "agent module missing cmd_inbox_peek (RED: not implemented yet)"
    )


def test_inbox_peek_returns_entries_without_consuming(tmp_path):
    """cmd_inbox_peek twice returns the same entry both times."""
    from atdd.coach.commands.agent import cmd_inbox_peek

    agent_id = "inbox-peek-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    _write_cli_return(cli_return_path, "peeked correction\n")

    first = cmd_inbox_peek(agent_id=agent_id, runtime_root=tmp_path)
    second = cmd_inbox_peek(agent_id=agent_id, runtime_root=tmp_path)

    assert len(first) == 1, f"Expected 1 entry on first peek, got {first}"
    assert first == second, f"Peek not idempotent: first={first}, second={second}"


def test_inbox_peek_empty_when_no_entries(tmp_path):
    """peek on an empty cli-return.jsonl returns []."""
    from atdd.coach.commands.agent import cmd_inbox_peek

    agent_id = "inbox-peek-empty"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    result = cmd_inbox_peek(agent_id=agent_id, runtime_root=tmp_path)
    assert result == []


def test_peek_does_not_affect_subsequent_drain(tmp_path):
    """A peek does not affect a subsequent drain's result."""
    from atdd.coach.commands.agent import cmd_inbox_drain, cmd_inbox_peek

    agent_id = "inbox-peek-drain"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"

    _write_cli_return(cli_return_path, "only entry\n")

    peeked = cmd_inbox_peek(agent_id=agent_id, runtime_root=tmp_path)
    drained = cmd_inbox_drain(agent_id=agent_id, runtime_root=tmp_path)

    assert len(peeked) == 1
    assert len(drained) == 1
    assert peeked[0]["correction_text"] == drained[0]["correction_text"]


def test_inbox_peek_subcommand_registered_in_cli():
    """The 'inbox peek' action is registered in the CLI parser."""
    from atdd.coach.commands.agent import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["inbox", "peek", "--agent-id", "test-001"])
    assert args.subcommand == "inbox"
    assert args.inbox_action == "peek"
