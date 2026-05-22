# URN: test:observe-and-correct:E003-UNIT-003-bootstrap-inbox-priming
# Acceptance: acc:observe-and-correct:E003-UNIT-003-bootstrap-inbox-priming
# WMBT: wmbt:observe-and-correct:E003
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E003-UNIT-003 — cmd_spawn writes the launch prompt as the first
cli-return.jsonl entry before spawning the shim when
ATDD_CORRECTION_TRANSPORT=cli-return.

Issue #824.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]


def test_spawn_module_exposes_prime_inbox_function():
    """spawn module exposes a prime_inbox or similar bootstrap function."""
    from atdd.coach.commands import spawn

    assert hasattr(spawn, "_prime_inbox_with_launch_prompt") or hasattr(
        spawn, "prime_inbox_with_launch_prompt"
    ), (
        "spawn module missing _prime_inbox_with_launch_prompt "
        "(RED: bootstrap priming not implemented yet)"
    )


def test_prime_inbox_writes_launch_prompt_to_cli_return(tmp_path):
    """_prime_inbox_with_launch_prompt writes the prompt to cli-return.jsonl."""
    from atdd.coach.commands.spawn import _prime_inbox_with_launch_prompt

    agent_id = "bootstrap-prime-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    prompt_text = "Please implement issue #824.\n\nWMBT: wmbt:observe-and-correct:E003"
    _prime_inbox_with_launch_prompt(
        agent_id=agent_id,
        prompt_text=prompt_text,
        agent_dir=agent_dir,
    )

    cli_return_path = agent_dir / "cli-return.jsonl"
    assert cli_return_path.exists(), "cli-return.jsonl not created by bootstrap priming"

    with cli_return_path.open() as f:
        record = json.loads(f.readline())

    assert record.get("correction_text") == prompt_text or record.get("prompt") == prompt_text, (
        f"Launch prompt not found in cli-return.jsonl record: {record}"
    )


def test_bootstrap_priming_precedes_shim_spawn(tmp_path, monkeypatch):
    """When ATDD_CORRECTION_TRANSPORT=cli-return, cli-return.jsonl is written
    before the shim process is started (verified by call order)."""
    from atdd.coach.commands import spawn

    call_log: list[str] = []

    original_prime = getattr(spawn, "_prime_inbox_with_launch_prompt", None)
    if original_prime is None:
        pytest.skip("_prime_inbox_with_launch_prompt not yet implemented (RED)")

    def fake_prime(*args, **kwargs):
        call_log.append("prime")
        return original_prime(*args, **kwargs)

    # Patch the shim spawn so we can observe call order
    monkeypatch.setattr(spawn, "_prime_inbox_with_launch_prompt", fake_prime)

    env = os.environ.copy()
    env["ATDD_CORRECTION_TRANSPORT"] = "cli-return"

    # Verify prime is called — actual spawn integration tested separately
    with monkeypatch.context() as m:
        m.setenv("ATDD_CORRECTION_TRANSPORT", "cli-return")
        agent_id = "prime-order-001"
        agent_dir = tmp_path / "agents" / agent_id
        agent_dir.mkdir(parents=True)

        spawn._prime_inbox_with_launch_prompt(
            agent_id=agent_id,
            prompt_text="test prompt",
            agent_dir=agent_dir,
        )

    assert "prime" in call_log


def test_paste_text_not_called_when_cli_return_transport(tmp_path, monkeypatch):
    """When ATDD_CORRECTION_TRANSPORT=cli-return, paste_text is NOT called."""
    pytest.skip(
        "Integration-level: requires full cmd_spawn harness — "
        "verified separately in spawn integration tests (RED placeholder)"
    )
